"""按角色台词时间段提取原声，用本地 Demucs 分离人声和背景，并写入角色资产。"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import imageio_ffmpeg


class MissingAudio(ValueError):
    pass


def check_source(video):
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-i', str(video)],
        capture_output=True, text=True)
    if 'Input #' not in result.stderr:
        raise ValueError('无法读取输入文件：' + result.stderr[-1000:])
    if not re.search(r'Stream #.*Audio:', result.stderr):
        raise MissingAudio('输入文件没有音轨，无法提取人物原声。')


def save_record(character_dir, record):
    audio_dir = character_dir / 'audio'
    audio_dir.mkdir(exist_ok=True)
    (audio_dir / 'asset.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))
    character_file = character_dir / 'character.json'
    character = json.loads(character_file.read_text())
    character['audio_assets'] = record
    character_file.write_text(json.dumps(character, ensure_ascii=False, indent=2))


def extract_segment(video, start, end, target):
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v', 'error',
               '-i', str(video), '-ss', str(start), '-t', str(end - start),
               '-map', '0:a:0', '-vn', '-ac', '2', '-ar', '44100',
               '-c:a', 'pcm_s24le', str(target)]
    subprocess.run(command, check=True, capture_output=True, text=True)


def separate(original, voice, background, model):
    import numpy as np
    import soundfile as sf
    import torch
    from demucs.apply import apply_model

    samples, rate = sf.read(original, dtype='float32', always_2d=True)
    if len(samples) < rate // 2:
        raise ValueError('音频不足0.5秒，请检查时间段是否超出素材范围。')
    if not np.isfinite(samples).all() or float(np.max(np.abs(samples))) < 1e-6:
        raise ValueError('选中片段为空或静音，请另选有台词的时间段。')
    if rate != model.samplerate or samples.shape[1] != model.audio_channels:
        raise ValueError('音频采样率或通道数与分离模型不一致。')
    mixed = torch.from_numpy(samples.T.copy())
    reference = mixed.mean(0)
    mean, scale = reference.mean(), reference.std().clamp_min(1e-6)
    with torch.inference_mode():
        stems = apply_model(model, ((mixed - mean) / scale)[None],
                            device='cpu', shifts=0, overlap=0.25, progress=False)[0]
    vocal = (stems[model.sources.index('vocals')] * scale + mean).T.numpy()
    residual = samples - vocal
    if not np.isfinite(vocal).all() or not np.isfinite(residual).all():
        raise ValueError('分离结果包含无效采样。')
    if float(np.max(np.abs(vocal))) < 1e-6:
        raise ValueError('未分离出有效人声，请检查台词或更换片段。')
    # 使用同一增益保存人声和背景，避免独立归一化破坏两者的相对响度。
    peak = max(float(np.max(np.abs(vocal))), float(np.max(np.abs(residual))))
    gain = min(1.0, 0.99 / max(peak, 1e-6))
    sf.write(voice, vocal * gain, rate, subtype='PCM_24')
    sf.write(background, residual * gain, rate, subtype='PCM_24')
    return dict(duration_seconds=len(samples) / rate, sample_rate=rate,
                channels=samples.shape[1], output_gain=gain)


def extract_assets(video, clips, package):
    video, package = Path(video).resolve(), Path(package).resolve()
    if not video.is_file():
        raise ValueError('输入文件不存在。')
    if not clips:
        raise ValueError('至少选择一段角色台词。')
    ids = set()
    for clip in clips:
        cid, start, end = clip['character_id'], float(clip['start']), float(clip['end'])
        if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', cid):
            raise ValueError('角色编号含非法字符。')
        if cid in ids:
            raise ValueError('首版每个角色仅接受一段音频，请勿重复角色编号。')
        ids.add(cid)
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError('起止时间必须为有限数字，且满足0 <= start < end。')
        character_dir = package / f'character-{cid}'
        if not (character_dir / 'character.json').is_file():
            raise ValueError(f'角色{cid}没有人物资产记录。')
        if any((character_dir / 'audio' / name).exists()
               for name in ['original.wav', 'voice.wav', 'background.wav']):
            raise ValueError(f'角色{cid}已有人物音频，请使用新的资产包目录以保留旧版本。')
    missing_audio = None
    try:
        check_source(video)
    except MissingAudio as error:
        missing_audio = str(error)
    model, records = None, []
    for clip in clips:
        cid = clip['character_id']
        character_dir = package / f'character-{cid}'
        start, end = float(clip['start']), float(clip['end'])
        record = dict(character_id=cid, source=str(video), start_seconds=start,
                      end_seconds=end, selection_note=clip.get('selection_note', ''),
                      speaker_confirmation='pending_review', original=None,
                      voice=None, background=None, status='source_has_no_audio')
        if missing_audio:
            record['reason'] = missing_audio
        else:
            with tempfile.TemporaryDirectory(prefix='drama-audio-') as work:
                work = Path(work)
                original, voice, background = [work / n for n in
                                               ['original.wav', 'voice.wav', 'background.wav']]
                extract_segment(video, start, end, original)
                import numpy as np
                import soundfile as sf
                info = sf.info(original)
                if info.duration < end - start - 0.1:
                    raise ValueError(f'角色{cid}时间段超出素材长度，请重新选择。')
                samples, _ = sf.read(original, dtype='float32', always_2d=True)
                if info.duration < 0.5 or not np.isfinite(samples).all() or np.max(np.abs(samples)) < 1e-6:
                    raise ValueError(f'角色{cid}片段过短或静音，请重新选择台词。')
                if model is None:
                    import torch
                    from demucs.pretrained import get_model
                    torch.set_num_threads(4)
                    model = get_model('htdemucs').eval()
                record.update(separate(original, voice, background, model))
                audio_dir = character_dir / 'audio'
                audio_dir.mkdir(exist_ok=True)
                for name, path in [('original', original), ('voice', voice), ('background', background)]:
                    shutil.copy2(path, audio_dir / path.name)
                    record[name] = f'character-{cid}/audio/{path.name}'
            record.update(status='processed_review_pending', method='demucs-htdemucs',
                          note='人声分离会抑制背景音乐和部分环境声，可能有残留或音色损伤；不能自动隔离重叠说话人。')
        save_record(character_dir, record)
        records.append(record)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True)
    parser.add_argument('--clips', required=True, help='角色编号与台词起止时间的JSON')
    parser.add_argument('--package', required=True, help='已有角色资产包目录')
    args = parser.parse_args()
    try:
        records = extract_assets(args.video, json.loads(Path(args.clips).read_text()), args.package)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, RuntimeError) as error:
        parser.exit(1, f'音频提取失败：{error}\n')
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 2 if any(r['status'] == 'source_has_no_audio' for r in records) else 0


if __name__ == '__main__':
    raise SystemExit(main())
