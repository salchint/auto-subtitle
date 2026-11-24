import os
import ffmpeg
import whisper
import argparse
import warnings
import tempfile
from .utils import filename, str2bool, write_srt, split_segments, hex2ass, POSITIONS, LEGACY_ALIGNMENT
from .ass import write_ass


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("video", nargs="+", type=str,
                        help="paths to video files to transcribe")
    parser.add_argument("--model", default="small",
                        choices=whisper.available_models(), help="name of the Whisper model to use")
    parser.add_argument("--output_dir", "-o", type=str,
                        default=".", help="directory to save the outputs")
    parser.add_argument("--output_srt", type=str2bool, default=False,
                        help="whether to output the .srt file along with the video files")
    parser.add_argument("--srt_only", type=str2bool, default=False,
                        help="only generate the .srt file and not create overlayed video")
    parser.add_argument("--verbose", type=str2bool, default=False,
                        help="whether to print out the progress and debug messages")

    parser.add_argument("--task", type=str, default="transcribe", choices=[
                        "transcribe", "translate"], help="whether to perform X->X speech recognition ('transcribe') or X->English translation ('translate')")
    parser.add_argument("--language", type=str, default="auto", choices=["auto","af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs","cy","da","de","el","en","es","et","eu","fa","fi","fo","fr","gl","gu","ha","haw","he","hi","hr","ht","hu","hy","id","is","it","ja","jw","ka","kk","km","kn","ko","la","lb","ln","lo","lt","lv","mg","mi","mk","ml","mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl","ps","pt","ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw","ta","te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo","zh"], 
    help="What is the origin language of the video? If unset, it is detected automatically.")

    style = parser.add_argument_group("subtitle style")
    style.add_argument("--font", type=str, default="Aerolite",
                       help="name of an installed font to render the subtitles with")
    style.add_argument("--font_size", type=int, default=18,
                       help="font size (relative to a 288px-high canvas, scaled to the video)")
    style.add_argument("--font_colour", "--font_color", type=hex2ass, default="#1B2A4A",
                       help="text colour as #RRGGBB or #RRGGBBAA (AA = opacity); default is dark navy blue")
    style.add_argument("--background_colour", "--background_color", type=hex2ass, default="#F2C14ECC",
                       help="colour of the box behind the text as #RRGGBB or #RRGGBBAA; default is warm gold at 80% opacity")
    style.add_argument("--position", type=str, default="bottom", choices=list(POSITIONS),
                       help="where on the screen to place the subtitles")
    style.add_argument("--max_lines", type=int, default=1,
                       help="maximum number of lines shown at once")
    style.add_argument("--max_line_width", type=int, default=42,
                       help="maximum characters per line; 0 keeps Whisper's original (often long) segments")
    style.add_argument("--animation", type=str, default="none", choices=["none", "karaoke", "pop"],
                       help="word-by-word animation: 'karaoke' colours the word being spoken, "
                            "'pop' makes each word pop in as it is spoken")
    style.add_argument("--highlight_colour", "--highlight_color", type=hex2ass, default="#A4161A",
                       help="colour of the spoken word with --animation karaoke; default is deep crimson")

    args = parser.parse_args().__dict__
    model_name: str = args.pop("model")
    output_dir: str = args.pop("output_dir")
    output_srt: bool = args.pop("output_srt")
    srt_only: bool = args.pop("srt_only")
    language: str = args.pop("language")
    style = {key: args.pop(key) for key in (
        "font", "font_size", "font_colour", "background_colour", "highlight_colour")}
    style["alignment"] = POSITIONS[args.pop("position")]
    animation: str = args.pop("animation")
    max_lines: int = args.pop("max_lines")
    max_line_width: int = args.pop("max_line_width")
    if max_lines < 1 or max_line_width < 0:
        parser.error("--max_lines must be >= 1 and --max_line_width must be >= 0")
    split = bool(max_line_width) or animation != "none"
    if split:
        # per-word timings let us split long segments into short, correctly
        # timed cues and animate individual words
        args["word_timestamps"] = True

    os.makedirs(output_dir, exist_ok=True)

    if model_name.endswith(".en"):
        warnings.warn(
            f"{model_name} is an English-only model, forcing English detection.")
        args["language"] = "en"
    # if translate task used and language argument is set, then use it
    elif language != "auto":
        args["language"] = language
        
    model = whisper.load_model(model_name)
    audios = get_audio(args.pop("video"))
    subtitles = get_subtitles(
        audios, output_srt or srt_only, output_dir, lambda audio_path: model.transcribe(audio_path, **args),
        max_lines, max_line_width if split else None
    )

    if srt_only:
        return

    for path, (srt_path, cues) in subtitles.items():
        out_path = os.path.join(output_dir, f"{filename(path)}.mp4")

        print(f"Adding subtitles to {filename(path)}...")

        video = ffmpeg.input(path)
        audio = video.audio

        if animation == "none":
            subtitled = video.filter('subtitles', srt_path, force_style=force_style(style))
        else:
            # animations need per-word styling, which only the ASS format offers
            ass_path = os.path.splitext(srt_path)[0] + ".ass"
            width, height = video_size(path)
            with open(ass_path, "w", encoding="utf-8") as ass:
                write_ass(cues, ass, style, width, height, animation)
            subtitled = video.filter('subtitles', ass_path)

        ffmpeg.concat(subtitled, audio, v=1, a=1).output(out_path).run(
            quiet=True, overwrite_output=True)

        print(f"Saved subtitled video to {os.path.abspath(out_path)}.")


def force_style(style: dict) -> str:
    return ",".join([
        f"FontName={style['font']}",
        f"FontSize={style['font_size']}",
        f"PrimaryColour={style['font_colour']}",
        # with BorderStyle=3 libass fills the box behind the text with OutlineColour
        f"OutlineColour={style['background_colour']}",
        "BorderStyle=3",
        "Outline=1",
        "Shadow=0",
        f"Alignment={LEGACY_ALIGNMENT[style['alignment']]}",
    ])


def video_size(path: str):
    """Displayed width and height of a video, taking rotation metadata into account."""
    stream = next(s for s in ffmpeg.probe(path)["streams"] if s["codec_type"] == "video")
    width, height = int(stream["width"]), int(stream["height"])
    rotation = stream.get("tags", {}).get("rotate") or next(
        (d.get("rotation") for d in stream.get("side_data_list", []) if "rotation" in d), 0)
    if abs(int(float(rotation))) % 180 == 90:
        width, height = height, width
    return width, height


def get_audio(paths):
    temp_dir = tempfile.gettempdir()

    audio_paths = {}

    for path in paths:
        print(f"Extracting audio from {filename(path)}...")
        output_path = os.path.join(temp_dir, f"{filename(path)}.wav")

        ffmpeg.input(path).output(
            output_path,
            acodec="pcm_s16le", ac=1, ar="16k"
        ).run(quiet=True, overwrite_output=True)

        audio_paths[path] = output_path

    return audio_paths


def get_subtitles(audio_paths: list, output_srt: bool, output_dir: str, transcribe: callable,
                  max_lines: int = 1, max_line_width: int = None):
    """Transcribe each audio file and write its .srt. max_line_width=None keeps
    Whisper's segments as they are; 0 splits into cues without a width limit.
    Returns {video path: (srt path, cues)}."""
    subtitles_path = {}

    for path, audio_path in audio_paths.items():
        srt_path = output_dir if output_srt else tempfile.gettempdir()
        srt_path = os.path.join(srt_path, f"{filename(path)}.srt")
        
        print(
            f"Generating subtitles for {filename(path)}... This might take a while."
        )

        warnings.filterwarnings("ignore")
        result = transcribe(audio_path)
        warnings.filterwarnings("default")

        with open(srt_path, "w", encoding="utf-8") as srt:
            segments = result["segments"]
            if max_line_width is not None:
                segments = split_segments(segments, max_lines, max_line_width)
            write_srt(segments, file=srt)

        subtitles_path[path] = (srt_path, segments)

    return subtitles_path


if __name__ == '__main__':
    main()
