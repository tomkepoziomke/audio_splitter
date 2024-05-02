import pydub
from pydub import silence

import re
import os
from dataclasses import dataclass
from pathvalidate import sanitize_filepath
import argparse

@dataclass
class SongInfo:
    '''
        Dataclass representing basic song info.
    '''
    artist: str
    album: str
    title: str
    year: int
    track_number: int
    duration: int

class GUI:
    '''
        Class for displaying information useful to the user.
    '''

    MAX_TITLE_LENGTH = 20
    
    class Color:
        RED     = '\033[91m'
        GREEN   = '\033[92m'
        YELLOW  = '\033[93m'
        BLUE    = '\033[94m'
        NONE    = '\033[0m'

    def __init__(self, info_color = Color.BLUE, accent_color = Color.GREEN, warning_color = Color.RED, default_color = Color.NONE):
        self.info_color = info_color
        self.accent_color = accent_color
        self.warning_color = warning_color
        self.default_color = default_color

    def info(self, message: str, header: str | None = None):
        string = f'{self.info_color}{'Info' if header == None else header}: {self.default_color}{message}'
        print(string)

    def warn(self, message: str, header: str | None = None):
        string = f'{self.warning_color}{'Warn' if header == None else header}: {self.default_color}{message}'
        print(string)

    def log_parse(self, track: SongInfo):
        title = self._ellipsis(track.title, GUI.MAX_TITLE_LENGTH)
        self.info(message = f'{title} ({self.accent_color}{duration_millis_to_str(track.duration, short = True)}{self.default_color})', header = 'Parsing track')

    def log_splice(self, begin: int, end: int):
        self.info(message = f'splicing audio at {self.accent_color}{duration_millis_to_str(begin)}{self.default_color} - {self.accent_color}{duration_millis_to_str(end)}{self.default_color}')

    def warn_skip(self, begin: int, end: int):
        self.warn(message = f'silence at {self.accent_color}{duration_millis_to_str(begin)}{self.default_color} skipped ({end - begin} ms)')
    
    def _ellipsis(self, title: str, length: int):
        title = title.strip() 
        title = title if len(title) <= length else title[:length - 1].strip() + '...'
        title = f'\"{title}\"'
        return title

    def log_export(self, segment: pydub.AudioSegment, tags: dict):
        title = self._ellipsis(tags.title, GUI.MAX_TITLE_LENGTH)
        self.info(f'{title:25s}({segment.dBFS:-6.2f} dBFS, {duration_millis_to_str(len(segment), short = True)})' , header = 'Exporting track')

gui = GUI()


class Defaults:
    OUTPUT_DIRECTORY    = './out'
    LOUDNESS            = None
    TOLERANCE           = 0
    MIN_SILENCE_LENGTH  = 100
    SILENCE_THRESHOLD   = -70
    SEEK_STEP           = 20

def duration_string_to_millis(duration: str):

    '''
        Attempts to convert mm:ss string to length in milliseconds (mm * 60 * 1000 + ss * 1000).
        If unsuccessful, returns -1.
    '''

    chunks = duration.split(':')
    if len(chunks) != 2:
        return -1
    minutes, seconds = 0, 0
    try:
        minutes = int(chunks[0])
        seconds = int(chunks[1])
    except Exception as _:
        return -1
    
    if minutes < 0 or seconds < 0:
        return -1
    
    return minutes * 60 * 1000 + seconds * 1000

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

def parse_album_info(album_path: str):

    '''
        Parses album info in the file given by the album_path.
        The file is a key-value pair combination of the following format:

        Album: album_title
        Artist: artist_name
        Year: album_year
        1. "song_number_one"  mm:ss
        2. "song_number_two"  mm:ss
        
        etc.
    '''

    lines = []
    with open(album_path, "r", encoding = 'utf-8') as file:
        lines = file.readlines()
        lines = [line.strip() for line in lines if line.strip() != '']

    album_regex = re.compile(r'^\s*Album:\s*([^\s].*[^\s])\s*$')
    artist_regex = re.compile(r'^\s*Artist:\s*([^\s].*[^\s])\s*$')
    year_regex = re.compile(r'^\s*Year:\s*(\d+)\s*$')
    song_regex = re.compile(r'^\s*(\d+)\.\s*"(.*)".*\b(\d+:\d+)\s*$')

    tracks = []
    album = ''
    artist = ''
    year = ''
    
    for line in lines:
        if (match := album_regex.match(line)):
            album = str(match[1])
        elif (match := artist_regex.match(line)):
            artist = str(match[1])
        elif (match := year_regex.match(line)):
            year = int(match[1])
        elif (match := song_regex.match(line)):
            number = int(match[1])
            title = str(match[2])
            duration = duration_string_to_millis(match[3])
            duration = max(duration, 0)
            tracks.append(SongInfo(artist, album, title, year, number, duration))
        
    return tracks

def strip_audio_segment(audio: pydub.AudioSegment, silence_threshold: int = Defaults.SILENCE_THRESHOLD):
    '''
        Strips leading and trailing silence from a segment.
    '''
    leading_silence = silence.detect_leading_silence(audio, silence_threshold = silence_threshold, chunk_size = Defaults.SEEK_STEP)
    trailing_silence = silence.detect_leading_silence(audio.reverse(), silence_threshold = silence_threshold, chunk_size = Defaults.SEEK_STEP)
    trailing_silence = max(trailing_silence, 1) # without this, list comprehension looks like [:-0] which is utterly different to [:-1]!
    audio = audio[leading_silence:-trailing_silence]
    return audio, leading_silence, trailing_silence

def process_audio_into_segments(audio_path: str, 
                                tracklist: list, 
                                tolerance: int = Defaults.TOLERANCE, 
                                target_dBFS: float | None = Defaults.LOUDNESS,
                                silence_threshold: int = Defaults.SILENCE_THRESHOLD,
                                min_silence_length: int = Defaults.MIN_SILENCE_LENGTH):

    '''
        Given a path to an audio file and an already processed list of tracks,
        attempts to split the file into chunks with accordance to the list.
    '''
    audio_path = sanitize_filepath(audio_path)
    audio = pydub.AudioSegment.from_file(audio_path)


    # trimming leading and trailing silence
    audio, leading_silence, trailing_silence = strip_audio_segment(audio, silence_threshold)
    
    # calculating dBFS and adjusting
    if target_dBFS != None:
        audio_loudness = audio.dBFS
        audio += (target_dBFS - audio_loudness)

    # detecting other silent segments
    silent_segments = silence.detect_silence(audio, min_silence_len = min_silence_length, silence_thresh = silence_threshold, seek_step = Defaults.SEEK_STEP)
    silent_segments.append([len(audio), len(audio)]) # artificially adding silence after the last track, so the following logic still holds for the last song
    silent_gen = (silence for silence in silent_segments)

    audio_segments = []
    time_offset = 0
    for track in tracklist:
        
        gui.log_parse(track)

        while (silent_segment := next(silent_gen, None)):
            silence_begin = silent_segment[0] - time_offset
            silence_end = silent_segment[1] - time_offset
            if track.duration - tolerance <= silence_end:
                audio_segment, _, _ = strip_audio_segment(audio[:silence_begin])
                audio_segments.append((audio_segment, track))
                audio = audio[silence_end:]
                time_offset += silence_end
                gui.log_splice(silent_segment[0] + leading_silence, silent_segment[1] + leading_silence)
                break
            else:
                gui.warn_skip(silent_segment[0] + leading_silence, silent_segment[1] + leading_silence)
    return audio_segments

def export_audio_segments(segments, output_dir = '.'):
    '''
        Exports segments track-by-track to the output directory.
    '''

    def sanitize_title(title: str):
        '''
            Sanitizes track title (for proper export, e.g. replaces slashes so the tokens preceding are not interpreted as a folder).
        '''
        title = sanitize_filepath(title)
        title = title.replace(r'/', ' ')
        title = title.replace('\\', ' ')
        return title

    output_dir = sanitize_filepath(output_dir)
    for segment, tags in segments:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        gui.log_export(segment, tags)
        segment.export(output_dir + '/' + sanitize_title(tags.title) + '.mp3', format = 'mp3', bitrate = "192k", tags = {
            "album": tags.album,
            "artist": tags.artist,
            "date": tags.year,
            "title": tags.title,
            "track": tags.track_number
        })


def main(args):
    tracklist = parse_album_info(args.tracklist)
    segments = process_audio_into_segments(args.input, tracklist, args.tolerance, args.loudness, args.silence_threshold, args.silence_duration)
    export_audio_segments(segments, args.output)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input', help = 'Audio file to be split.', required = True)
    parser.add_argument('-l', '--tracklist', help = 'Tracklist of the album.', required = True)
    parser.add_argument('-o', '--output', help = f'Output directory (default: {Defaults.OUTPUT_DIRECTORY}).', default = Defaults.OUTPUT_DIRECTORY)
    parser.add_argument('-t', '--tolerance', type = int, help = f'Margin of error (in ms) for track lengths (default: {Defaults.TOLERANCE}).', default = Defaults.TOLERANCE)
    parser.add_argument('-v', '--loudness', type = float, help = f'Adjusts average dBFS loudness to the given level (default: {Defaults.LOUDNESS}).', default = Defaults.LOUDNESS)
    parser.add_argument('-s', '--silence_threshold', type = int, help = f'Sets the silence threshold, e.g. the dBFS value below which audio is considered silence (default: {Defaults.SILENCE_THRESHOLD}).', default = Defaults.SILENCE_THRESHOLD)
    parser.add_argument('-d', '--silence_duration', type = int, help = f'Sets the minimum silence duration, e.g. silent segments below this duration will not be considered silent (default: {Defaults.MIN_SILENCE_LENGTH}).', default = Defaults.MIN_SILENCE_LENGTH)
    args = parser.parse_args()
    main(args)