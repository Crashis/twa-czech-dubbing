"""Resumable offline STT evidence; requires separately installed faster-whisper.

Accepts explicit local model and WAV paths. Never downloads a model or uploads
audio. Hypotheses are evidence, not human listening or confirmed transcripts.
"""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', required=True)
    parser.add_argument('--model-directory', required=True)
    parser.add_argument('--model-label', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--shard', default='0/1')
    parser.add_argument('--leading-silence', type=float, default=0,
                        help='Optional analysis-only zero prefix in seconds; original WAV is unchanged')
    parser.add_argument('--beam-size', type=int, default=5)
    args = parser.parse_args()
    model_path = Path(args.model_directory).resolve(strict=True)
    if not (model_path / 'model.bin').is_file():
        raise ValueError('Explicit local model.bin required; downloads are disabled')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from faster_whisper import WhisperModel
    import av
    import numpy as np
    model = WhisperModel(str(model_path), device='cpu', compute_type='int8', cpu_threads=args.threads,
                         local_files_only=True)
    output = Path(args.output)
    done = json.loads(output.read_text(encoding='utf-8'))['results'] if output.exists() else {}
    shard, count = map(int, args.shard.split('/'))
    jobs = [j for i, j in enumerate(json.loads(Path(args.jobs).read_text(encoding='utf-8')))
            if i % count == shard and j['key'] not in done]
    started = time.monotonic()
    provenance = {'model': args.model_label, 'engine': 'faster-whisper CPU int8', 'language': 'en',
                  'beam_size': args.beam_size, 'temperature': 0, 'initial_prompt': None, 'hotwords': None,
                  'vad_filter': False, 'audio_uploaded': False, 'offline': True}
    provenance['analysis_leading_silence_seconds'] = args.leading_silence
    for i, job in enumerate(jobs):
        resampler = av.AudioResampler(format='fltp', layout='mono', rate=16000)
        frames = []
        with av.open(job['wav']) as container:
            for frame in container.decode(audio=0):
                frames.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
            frames.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(None))
        audio = np.concatenate(frames)
        if args.leading_silence:
            audio = np.concatenate([np.zeros(round(16000*args.leading_silence), dtype=np.float32), audio])
        segments, _ = model.transcribe(audio, language='en', beam_size=args.beam_size, temperature=0,
                                      condition_on_previous_text=False, vad_filter=False,
                                      initial_prompt=None, without_timestamps=True)
        segments = list(segments)
        done[job['key']] = {'text': ''.join(s.text for s in segments).strip(),
                            'avg_logprob': min((s.avg_logprob for s in segments), default=None),
                            'no_speech_prob': max((s.no_speech_prob for s in segments), default=None)}
        if i % 10 == 0 or i == len(jobs) - 1:
            temporary = output.with_suffix('.partial')
            temporary.write_text(json.dumps(provenance | {'results': done}, ensure_ascii=False, indent=1), encoding='utf-8')
            temporary.replace(output)
        if i % 25 == 0 or i == len(jobs) - 1:
            print(args.model_label, i + 1, '/', len(jobs), round(time.monotonic()-started), 's', flush=True)


if __name__ == '__main__':
    main()
