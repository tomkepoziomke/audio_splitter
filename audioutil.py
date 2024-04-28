import argparse
import glob
import hashlib
import pydub
from pathvalidate import sanitize_filepath
from pydub import silence
import os
import re
from tinytag import TinyTag

class Defaults:
    OUTPUT_DIRECTORY    = './out'
    LOUDNESS            = None
    TOLERANCE           = 0
    MIN_SILENCE_LENGTH  = 100
    SILENCE_THRESHOLD   = -70
    SEEK_STEP           = 20

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

def _file_hash(filename: str):
    '''
        Returns the SHA1 hash of a file (to calculate duplicates during the scan).
    '''
    hl = hashlib.sha1()
    with open(filename, 'rb') as file:
        while True:
            chunk = file.read(1024)
            if not chunk:
                break
            hl.update(chunk)
    return hl.hexdigest()

def scan_for_segments(patterns):
    '''
        Scans for audio files matching one of the pattern from the list.
    '''
    matches = []
    for pattern in patterns:
        matches += glob.glob(pattern, recursive = True)
    segments = {}
    for match in matches:
        match_hash = _file_hash(match)
        if match_hash not in segments:
            segments[match_hash] = (match, pydub.AudioSegment.from_file(match))
    return segments.values()
    
def segments_info(segments):
    '''
        Displays file info for each of the audio segments.
    '''
    for path, segment in segments:
        print(f'Audio file: {path}')
        print(f'Duration: {duration_millis_to_str(len(segment)):10s} | Loudness: {segment.dBFS:3.2f} dbFS')

def segments_strip(segments: list, silence_threshold: int = Defaults.SILENCE_THRESHOLD):
    '''
        Trims leading and ending silence from audio segments.
    '''
    trimmed_segments = []
    for path, segment in segments:
        leading_silence = silence.detect_leading_silence(segment, silence_threshold = silence_threshold, chunk_size = Defaults.SEEK_STEP)
        ending_silence = silence.detect_leading_silence(segment.reverse(), silence_threshold = silence_threshold, chunk_size = Defaults.SEEK_STEP)
        ending_silence = max(ending_silence, 1) # without this, list comprehension looks like [:-0] which is utterly different to [:-1]!
        segment = segment[leading_silence:-ending_silence]
        trimmed_segments.append((path, segment))
    return trimmed_segments

def segments_loudness(segments, volume):
    '''
        Adjusts the loudness of the segments (by `volume` dB).
    '''
    adjusted_segments = []
    for path, segment in segments:
        adjusted_segments.append((path, segment + volume))
    return adjusted_segments

def _get_simple_audio_metadata(filename: str):
    tag = TinyTag.get(filename)
    tags = {
            "album": tag.album,
            "artist": tag.artist,
            "date": tag.year,
            "title": tag.title,
            "track": tag.track
    }
    return tags

def segments_average(segments, target_loudness):
    '''
        Adjusts the loudness of the segments to average out to `target loudness` dBFS.
    '''
    audio = pydub.AudioSegment.empty()
    for path, segment in segments:
        audio += segment
    current_loudness = audio.dBFS
    difference = target_loudness - current_loudness
    adjusted_segments = []
    for path, segment in segments:
        adjusted_segments.append((path, segment + difference))
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
        
        print(f'Exporting adjusted track: {os.path.basename(path)} ({duration_millis_to_str(len(segment), short = True)}, {segment.dBFS:.2f} dBFS)')
        tags = _get_simple_audio_metadata(path)
        segment.export(sanitize_filepath(output_dir + '/' + os.path.basename(path)), format = 'mp3', bitrate = '192k', tags = tags)

def main(args):
    audio_segments = scan_for_segments(args.input)
    export = False
    if args.list:
        segments_info(audio_segments)
    if args.strip:
        audio_segments = segments_strip(audio_segments, args.strip)
        export = True
    if args.loudness:
        audio_segments = segments_loudness(audio_segments, args.loudness)
        export = True
    if args.average:
        audio_segments = segments_average(audio_segments, args.average)
        export = True
    if export:
        segments_export(audio_segments, args.output)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', help = 'Audio files to manipulate. Supports basic Unix shell-style wildcards.', required = True, nargs = '+')
    parser.add_argument('-o', '--output', help = 'Output directory (default: ./out).', default = './out')
    parser.add_argument('-s', '--strip', help = f'Strips leading and trailing silence from the files below given dBFS (default: {Defaults.SILENCE_THRESHOLD}).', nargs = '?', type = float, const = Defaults.SILENCE_THRESHOLD)
    parser.add_argument('-v', '--loudness', help = 'Changes the loudness in the files by specified dB value.', type = float)
    parser.add_argument('-a', '--average', help = 'Averages the loudness of the files to the specified dBFS value.', type = float)
    parser.add_argument('-l', '--list', help = 'Displays info of audio files matching search criteria.', action = 'store_true')
    args = parser.parse_args()

    main(args)
    