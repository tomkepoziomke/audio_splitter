import argparse
import glob
import pydub
from pathvalidate import sanitize_filepath
from pydub import silence
import os
import re

def duration_millis_to_str(duration: int, short: bool = False):

    '''
        Attempts to convert milliseconds to dd:hh:mm:ss.lll format.
    '''
    dd, hh, mm, ss, lll = 0, 0, 0, 0, 0
    sign = '' if duration >= 0 else '-'
    duration = abs(duration)
    lll = duration % 1000
    duration = duration // 1000
    ss = duration % 60
    duration = duration // 60
    mm = duration % 60
    duration = duration // 60
    hh = duration % 24
    duration = duration // 24
    dd = duration
    
    if dd > 0:
        return f'{sign}{str(dd).zfill(2)}:{str(hh).zfill(2)}:{str(mm).zfill(2)}:{str(ss).zfill(2)}{'.' + str(lll).zfill(3) if not short else ''}'
    elif hh > 0:
        return f'{sign}{str(hh).zfill(2)}:{str(mm).zfill(2)}:{str(ss).zfill(2)}{'.' + str(lll).zfill(3) if not short else ''}'
    else:
        return f'{sign}{str(mm).zfill(2)}:{str(ss).zfill(2)}{'.' + str(lll).zfill(3) if not short else ''}'


def scan_for_segments(patterns):
    '''
        Scans for audio files matching one of the pattern from the list.
    '''
    matches = []
    for pattern in patterns:
        matches += glob.glob(pattern, recursive = True)
    segments = []
    for match in matches:
        segments.append((match, pydub.AudioSegment.from_file(match)))
    return segments
    
def segments_info(segments):
    '''
        Displays file info for each of the audio segments.
    '''
    for path, segment in segments:
        print(f'Audio file: {path}')
        print(f'  Duration: {duration_millis_to_str(len(segment)):10s} | Loudness: {segment.dBFS:3.2f} dbFS | Sample rate: {segment.frame_rate} Hz')

def segments_trim(segments):
    '''
        Trims leading and ending silence from audio segments.
    '''
    trimmed_segments = []
    MIN_SILENCE_LENGTH_MS   = 10
    SILENCE_THRESHOLD_DB    = -70
    SEEK_STEP_MS            = 2

    for path, segment in segments:
        leading_silence = silence.detect_leading_silence(segment, silence_threshold = SILENCE_THRESHOLD_DB, chunk_size = SEEK_STEP_MS)
        ending_silence = silence.detect_leading_silence(segment.reverse(), silence_threshold = SILENCE_THRESHOLD_DB, chunk_size = SEEK_STEP_MS)
        ending_silence = max(ending_silence, 1) # without this, list comprehension looks like [:-0] which is utterly different to [:-1]!
        segment = segment[leading_silence:-ending_silence]
        trimmed_segments.append((path, segment))
    return trimmed_segments

def segments_volume(segments, volume):
    '''
        Adjusts the volume of the segments (by `volume` dB).
    '''
    adjusted_segments = []
    for path, segment in segments:
        adjusted_segments.append((path, segment + volume))
    return adjusted_segments

def segments_export(segments, output_dir):
    '''
        Exports the segments to the output directory.
    '''
    output_dir = sanitize_filepath(output_dir)
    print(f'\nExporting tracks at 192k bitrate to output directory: {output_dir}')
    for path, segment in segments:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        replaced_path = re.sub(r'[\/\\]', '_', path)
        print(f'Exporting adjusted track: {replaced_path} ({duration_millis_to_str(len(segment), short = True)}, {segment.dBFS:.2f} dBFS)')
        segment.export(sanitize_filepath(output_dir + '/' + replaced_path))

def main(args):
    audio_segments = scan_for_segments(args.input)
    export = False
    if args.list:
        segments_info(audio_segments)
    if args.trim:
        audio_segments = segments_trim(audio_segments)
        export = True
    if args.volume != 0:
        audio_segments = segments_volume(audio_segments, args.volume)
        export = True
    if export:
        segments_export(audio_segments, args.output)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', help = 'Audio files to manipulate. Supports basic Unix shell-style wildcards.', required = True, nargs = '+')
    parser.add_argument('-o', '--output', help = 'Output directory (default: ./out).', default = './out')
    parser.add_argument('-t', '--trim', help = 'Trims leading and ending silence in the files.', action = 'store_true')
    parser.add_argument('-v', '--volume', help = 'Changes the loudness in the files by specified dB value.', type = int, default = 0)
    parser.add_argument('-l', '--list', help = 'Displays info of audio files matching search criteria.', action = 'store_true')
    args = parser.parse_args()

    main(args)
    