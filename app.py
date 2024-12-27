import streamlit as st
from moviepy import VideoFileClip, AudioFileClip, CompositeVideoClip
import os

import re

def extract_number(filename):
    match = re.search(r'clip(\d+)', filename)
    return int(match.group(1)) if match else float('inf')

def generate_montage(
    song_path: str,
    clips_info: list,
    beat_drops: list,
    output_path: str = "fortnite_montage_synced.mp4",
    fps: int = 60
):
    """
    Revised approach to:
    1) For the first clip: capture from 0s to kill_time + 1s in local clip time.
       Place it so the kill is pinned to beat_drops[0].
    2) For each subsequent clip i:
       - The final timeline start is 1s after the *previous clip's kill* 
         (which is pinned at its previous beat_drops[i-1]).
       - Subclip range in local time: [local_start_i, kill_time_i + 1].
         Where local_start_i is calculated so that the kill pins to beat_drops[i].
    """

    audio_clip = AudioFileClip(song_path)
    placed_clips = []

    # Keep track of when the previous kill happens in the final timeline.
    # For clip i, the kill is pinned at beat_drops[i], so:
    #   previous_kill_in_final_timeline = beat_drops[i - 1]
    # Then we start the new clip at (previous_kill_in_final_timeline + 1).
    previous_kill_final_time = None

    for i, clip_data in enumerate(clips_info):
        clip_path = clip_data["clip_path"]
        kill_time = clip_data["kill_time"]  # local kill time within the clip
        beat_time = beat_drops[i]           # final timeline beat-drop time for this kill

        # Load the clip
        clip = VideoFileClip(clip_path)

        # -------------------------------------------------
        # 1) Calculate the local subclip bounds
        # -------------------------------------------------
        local_end = kill_time + 1  # always end at 1s after the kill (clamped later)

        if i == 0:
            # For the first clip: start at 0 in local time
            local_start = 0
        else:
            # For subsequent clips:
            # We want the final timeline start of this clip to be:
            #     final_start_of_this_clip = previous_kill_final_time + 1
            #
            # The kill must be pinned at beat_time:
            #     final_start_of_this_clip + (kill_time - local_start) = beat_time
            # => local_start = kill_time - (beat_time - final_start_of_this_clip)
            #
            # final_start_of_this_clip = (beat_drops[i-1] + 1)
            final_start_of_this_clip = previous_kill_final_time + 1

            local_start = kill_time - (beat_time - final_start_of_this_clip)

            # If that formula yields something negative (or bigger than the clip),
            # we clamp below. Because subclip can't start below 0 or past clip duration.
        
        # Clamp local_start and local_end
        local_start = max(0, local_start)
        local_start = min(local_start, clip.duration)  # can't exceed clip duration

        local_end = max(0, local_end)
        local_end = min(local_end, clip.duration)

        if local_start >= local_end:
            # If subclip is zero or negative in length,
            # skip or create a minimal subclip to avoid black frames
            continue

        subclip = clip.subclipped(local_start, local_end)

        # -------------------------------------------------
        # 2) Calculate the final timeline offset
        # -------------------------------------------------
        # We know kill_time_in_subclip = (kill_time - local_start).
        kill_time_in_subclip = kill_time - local_start

        # We want that kill_time_in_subclip to align with beat_time in final timeline.
        # So: final_offset + kill_time_in_subclip = beat_time
        # => final_offset = beat_time - kill_time_in_subclip
        time_offset = beat_time - kill_time_in_subclip

        # This places the subclip in the final montage:
        subclip = subclip.with_start(time_offset)

        # -------------------------------------------------
        # 3) Update previous_kill_final_time for the next clip
        # -------------------------------------------------
        previous_kill_final_time = beat_time  # the kill is pinned at beat_time

        # Add subclip to the list
        placed_clips.append(subclip)

    # Composite everything
    final_video = CompositeVideoClip(placed_clips)

    # The final duration should be at least as long as the audio, or the last subclip
    final_duration = max(final_video.duration, audio_clip.duration)
    final_video = final_video.with_duration(final_duration)

    # Attach the audio
    final_audio = audio_clip.with_duration(final_duration)
    final_video = final_video.with_audio(final_audio)

    # Export
    final_video.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium"
    )
def main():
    st.title("Fortnite Montage Generator")

    # --- Song Uploader ---
    song_file = st.file_uploader("Upload your Song (MP3 or WAV)", type=["mp3", "wav"])
    if song_file:
        # Write the song to a temporary file
        song_path = os.path.join("temp_song." + song_file.name.split(".")[-1])
        with open(song_path, "wb") as f:
            f.write(song_file.read())
    else:
        song_path = None

    # --- Video Clips Uploader ---
    st.markdown("### Upload your Fortnite clips")
    clips_uploaded = st.file_uploader(
        "Upload multiple video clips",
        type=["mp4", "mov", "avi"],
        accept_multiple_files=True
    )
  # Sort the uploaded clips based on filename
    if clips_uploaded:
        clips_uploaded = sorted(
            clips_uploaded,
            key=lambda x: extract_number(x.name)
        )
    # --- Kill Times Input ---
    st.markdown("### Enter kill times (in seconds) for each clip")
    kill_times_input = st.text_input("Comma-separated kill times for each clip", value="13,8,11.5,11")

    # --- Beat Drops Input ---
    st.markdown("### Enter beat-drop times (in seconds) in the final timeline")
    beat_drops_input = st.text_input("Comma-separated beat drop times", value="8,10.5,13,17.5")

    # --- FPS Selection ---
    fps = st.number_input("FPS", value=60, min_value=1)

    # --- Generate Montage Button ---
    if st.button("Generate Montage"):
        if not song_path:
            st.warning("Please upload a song first.")
            return

        if not clips_uploaded:
            st.warning("Please upload at least one clip.")
            return

        # Parse kill times and beat drops
        try:
            kill_times = [float(x.strip()) for x in kill_times_input.split(",")]
            beat_drops = [float(x.strip()) for x in beat_drops_input.split(",")]
        except ValueError:
            st.error("Failed to parse kill_times or beat_drops. Please provide valid numeric values.")
            return

        if len(kill_times) != len(clips_uploaded):
            st.warning("Number of kill times must match the number of clips.")
            return

        if len(beat_drops) != len(clips_uploaded):
            st.warning("Number of beat drops must match the number of clips.")
            return

        # Write each clip to disk and collect info
        clips_info = []
        for i, clip_file in enumerate(clips_uploaded):
            clip_path = os.path.join("temp_clip_" + str(i) + "." + clip_file.name.split(".")[-1])
            with open(clip_path, "wb") as f:
                f.write(clip_file.read())

            clips_info.append({"clip_path": clip_path, "kill_time": kill_times[i]})

        # Generate the montage
        output_path = "final_montage.mp4"
        try:
            st.info("Processing... please wait.")
            generate_montage(song_path, clips_info, beat_drops, output_path=output_path, fps=fps)
            st.success("Montage generated successfully!")

            # Provide a download button for the user
            with open(output_path, "rb") as f:
                st.download_button(
                    label="Download Montage",
                    data=f,
                    file_name="montage.mp4",
                    mime="video/mp4"
                )

        except Exception as e:
            st.error(f"Error while generating montage: {e}")

if __name__ == "__main__":
    main()
