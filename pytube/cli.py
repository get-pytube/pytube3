#!/usr/bin/env python3
"""A simple command line application to download youtube videos."""

import argparse
import datetime as dt
import gzip
import json
import logging
import os
import sys
from io import BufferedWriter
from typing import Tuple, Any, Optional, List
import pathlib
import subprocess

from pytube import __version__, CaptionQuery, Stream
from pytube import YouTube
from pytube.helpers import safe_filename


logger = logging.getLogger(__name__)


def main():
    """Command line application to download youtube videos."""
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(description=main.__doc__)
    args = _parse_args(parser)
    logging.getLogger().setLevel(max(3 - args.verbosity, 0) * 10)

    if not args.url:
        parser.print_help()
        sys.exit(1)

    youtube = YouTube(args.url)
    print(youtube)

    if args.list:
        display_streams(youtube)
    if args.build_playback_report:
        build_playback_report(youtube)
    if hasattr(args, "caption_code"):
        download_caption(youtube=youtube, lang_code=args.caption_code)
    if args.ffmpeg:
        ff_best(youtube=youtube)    
    if args.itag:
        download_by_itag(youtube=youtube, itag=args.itag)
    if args.resolution:
        download_by_resolution(youtube=youtube, resolution=args.resolution)
    if args.audio:
        download_audio(youtube=youtube, filetype=args.audio)


def _parse_args(
    parser: argparse.ArgumentParser, args: Optional[List] = None
) -> argparse.Namespace:
    parser.add_argument("url", help="The YouTube /watch url", nargs="?")
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__,
    )
    parser.add_argument(
        "--itag", type=int, help="The itag for the desired stream",
    )
    parser.add_argument(
        "-r", "--resolution", type=str, help="The resolution for the desired stream",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help=(
            "The list option causes pytube cli to return a list of streams "
            "available to download"
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbosity",
        help="Verbosity level",
    )
    parser.add_argument(
        "--build-playback-report",
        action="store_true",
        help="Save the html and js to disk",
    )
    parser.add_argument(
        "-c",
        "--caption-code",
        type=str,
        default=argparse.SUPPRESS,
        nargs="?",
        help=(
            "Download srt captions for given language code. "
            "Prints available language codes if no argument given"
        ),
    )
    parser.add_argument(
        "-a",
        "--audio",
        const="mp4",
        nargs="?",
        help=(
            "Download the audio for a given URL at the highest bitrate available"
        )
    )
    parser.add_argument(
        "-f",
        "--ffmpeg",
        action="store_true",
        help=(
            "Creates a video using ffmpeg consisting of the highest res and abr \
            video and audio streams available of the same format"
        )
    )

    return parser.parse_args(args)


def build_playback_report(youtube: YouTube) -> None:
    """Serialize the request data to json for offline debugging.

    :param YouTube youtube:
        A YouTube object.
    """
    ts = int(dt.datetime.utcnow().timestamp())
    fp = os.path.join(
        os.getcwd(), "yt-video-{yt.video_id}-{ts}.json.gz".format(yt=youtube, ts=ts),
    )

    js = youtube.js
    watch_html = youtube.watch_html
    vid_info = youtube.vid_info

    with gzip.open(fp, "wb") as fh:
        fh.write(
            json.dumps(
                {
                    "url": youtube.watch_url,
                    "js": js,
                    "watch_html": watch_html,
                    "video_info": vid_info,
                }
            ).encode("utf8"),
        )


def get_terminal_size() -> Tuple[int, int]:
    """Return the terminal size in rows and columns."""
    dims = os.get_terminal_size()
    rows, columns = dims.lines, dims.columns
    return rows, columns


def display_progress_bar(
    bytes_received: int, filesize: int, ch: str = "█", scale: float = 0.55
) -> None:
    """Display a simple, pretty progress bar.

    Example:
    ~~~~~~~~
    PSY - GANGNAM STYLE(강남스타일) MV.mp4
    ↳ |███████████████████████████████████████| 100.0%

    :param int bytes_received:
        The delta between the total file size (bytes) and bytes already
        written to disk.
    :param int filesize:
        File size of the media stream in bytes.
    :param str ch:
        Character to use for presenting progress segment.
    :param float scale:
        Scale multiplier to reduce progress bar size.

    """
    _, columns = get_terminal_size()
    max_width = int(columns * scale)

    filled = int(round(max_width * bytes_received / float(filesize)))
    remaining = max_width - filled
    progress_bar = ch * filled + " " * remaining
    percent = round(100.0 * bytes_received / float(filesize), 1)
    text = " ↳ |{progress_bar}| {percent}%\r".format(
        progress_bar=progress_bar, percent=percent
    )
    sys.stdout.write(text)
    sys.stdout.flush()


def on_progress(
    stream: Any, chunk: Any, file_handler: BufferedWriter, bytes_remaining: int
) -> None:
    filesize = stream.filesize
    bytes_received = filesize - bytes_remaining
    display_progress_bar(bytes_received, filesize)


def _download(stream: Stream, output_path: Optional[str] = None) -> None:
    print("\n{fn} | {fs} bytes".format(fn=stream.default_filename, fs=stream.filesize))
    stream.download()
    sys.stdout.write("\n")


def download_by_itag(youtube: YouTube, itag: int) -> None:
    """Start downloading a YouTube video.

    :param YouTube youtube:
        A valid YouTube object.
    :param int itag:
        YouTube format identifier code.

    """
    # TODO(nficano): allow download target to be specified
    # TODO(nficano): allow dash itags to be selected
    stream = youtube.streams.get_by_itag(itag)
    if stream is None:
        print("Could not find a stream with itag: {itag}".format(itag=itag))
        print("Try one of these:")
        display_streams(youtube)
        sys.exit()

    youtube.register_on_progress_callback(on_progress)

    try:
        _download(stream)
    except KeyboardInterrupt:
        sys.exit()


def download_by_resolution(youtube: YouTube, resolution: str) -> None:
    """Start downloading a YouTube video.

    :param YouTube youtube:
        A valid YouTube object.
    :param str resolution:
        YouTube video resolution.

    """
    # TODO(nficano): allow download target to be specified
    # TODO(nficano): allow dash itags to be selected
    stream = youtube.streams.get_by_resolution(resolution)
    if stream is None:
        print(
            "Could not find a stream with resolution: {resolution}".format(
                resolution=resolution
            )
        )
        print("Try one of these:")
        display_streams(youtube)
        sys.exit()

    youtube.register_on_progress_callback(on_progress)

    try:
        _download(stream)
    except KeyboardInterrupt:
        sys.exit()


def download_audio(youtube: YouTube, filetype: str) -> None:
    """
    Start downloading a YouTube video.

    :param YouTube youtube:
        A valid YouTube object.
    :param str format:
        Desired file format to download.

    """
    audio = youtube.streams.filter(only_audio=True, subtype=filetype)\
        .order_by("abr").desc().first()

    if audio is None:
        print(
            "No audio only stream found. Try one of these:")
        display_streams(youtube)
        sys.exit()

    youtube.register_on_progress_callback(on_progress)

    try:
        _download(audio)
    except KeyboardInterrupt:
        sys.exit()


def display_streams(youtube: YouTube) -> None:
    """Probe YouTube video and lists its available formats.

    :param YouTube youtube:
        A valid YouTube watch URL.

    """
    for stream in youtube.streams.all():
        print(stream)


def _print_available_captions(captions: CaptionQuery) -> None:
    print(
        "Available caption codes are: {}".format(
            ", ".join(c.code for c in captions.all())
        )
    )


def download_caption(youtube: YouTube, lang_code: Optional[str]) -> None:
    """Download a caption for the YouTube video.

    :param YouTube youtube:
        A valid YouTube object.
    :param str lang_code:
        Language code desired for caption file.
        Prints available codes if the value is None
        or the desired code is not available.

    """
    if lang_code is None:
        _print_available_captions(youtube.captions)
        return

    caption = youtube.captions.get_by_language_code(lang_code=lang_code)
    if caption:
        downloaded_path = caption.download(title=youtube.title)
        print("Saved caption file to: {}".format(downloaded_path))
    else:
        print("Unable to find caption with code: {}".format(lang_code))
        _print_available_captions(youtube.captions)


def unique_name(base: str, subtype: str, video_audio: str) -> str:
    counter = 0
    while True:
        current_path = pathlib.Path.cwd()
        name = f"{base}_{video_audio}_{counter}"
        unique = current_path / f"{name}.{subtype}"

        if not unique.exists():
            return str(name)
        counter += 1


def ff_best(youtube: YouTube) -> None:
    youtube.register_on_progress_callback(on_progress)
    video_stream = youtube.streams.filter(progressive=False, subtype="mp4").order_by("resolution")\
    .desc().first()
    audio_stream = youtube.streams.filter(only_audio=True, subtype=video_stream.subtype)\
    .order_by("abr").desc().first()

    if not (video_stream and audio_stream):
        video_stream = youtube.streams.filter(progressive=False).order_by("resolution").desc().first()
        audio_stream = youtube.streams.filter(only_audio=True, subtype=video_stream.subtype)\
        .order_by("abr").desc().first()
    
    video_unique_name = unique_name(safe_filename(video_stream.title), video_stream.subtype, "video")
    audio_unique_name = unique_name(safe_filename(video_stream.title), video_stream.subtype, "audio")
    video_stream.download(filename=video_unique_name)
    audio_stream.download(filename=audio_unique_name)

    video_path = pathlib.Path.cwd() / f"{video_unique_name}.{video_stream.subtype}"
    audio_path = pathlib.Path.cwd() / f"{audio_unique_name}.{video_stream.subtype}"
    final_path = pathlib.Path.cwd() / f"{safe_filename(video_stream.title)}.{video_stream.subtype}"

    subprocess.run(["ffmpeg", "-i", f"{video_path}", "-i", f"{audio_path}",
    "-codec", "copy", f'{final_path}'])
    video_path.unlink()
    audio_path.unlink()    


if __name__ == "__main__":
    main()
