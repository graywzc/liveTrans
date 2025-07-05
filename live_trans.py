import whisper
import webrtcvad
import sounddevice as sd
import numpy as np
import wave
import os
import uuid
import time
import collections
import tkinter as tk
from tkinter import scrolledtext
from deep_translator import GoogleTranslator

# === Config ===
samplerate = 16000
channels = 1
frame_duration = 30  # ms
frame_size = int(samplerate * frame_duration / 1000)
buffer_duration = 10  # max buffer seconds
silence_timeout = 1.0  # end recording after this much silence
TARGET_LANGUAGE = "Japanese"

# === Init ===
model = whisper.load_model("small")  # You can use "tiny", "small", etc.
vad = webrtcvad.Vad(2)  # Aggressiveness: 0–3 (higher = more sensitive)

from pykakasi import Kakasi

def annotate_with_furigana(text):
    kakasi = Kakasi()
    result = ""

    for item in kakasi.convert(text):
        orig = item["orig"]
        hira = item["hira"]
        if orig != hira:
            result += f"{orig}({hira})"
        else:
            result += orig
    return result

def translate_japanese_to_english(text):
    try:
        translated = GoogleTranslator(source='ja', target='en').translate(text)
        return translated
    except Exception as e:
        return f"[Translation error: {e}]"

def create_subtitle_window():
    root = tk.Tk()
    root.title("Live Transcription (Japanese)")
    root.configure(bg='black')
    root.geometry("1000x400")

    text_widget = scrolledtext.ScrolledText(
        root,
        font=("Arial", 24),
        fg="white",
        bg="black",
        wrap=tk.WORD
    )
    text_widget.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    text_widget.insert(tk.END, "🔊 Listening for speech...\n")
    text_widget.config(state=tk.DISABLED)

    return root, text_widget


def is_speech(frame_bytes):
    return vad.is_speech(frame_bytes, sample_rate=samplerate)

def record_until_silence():
    audio_stream = sd.InputStream(samplerate=samplerate, channels=channels, dtype='int16', blocksize=frame_size)
    silence_start = None
    triggered = False
    voiced_frames = []

    with audio_stream:
        print("🎧 Waiting for speech...")
        while True:
            frame, _ = audio_stream.read(frame_size)
            frame_bytes = frame.tobytes()

            if is_speech(frame_bytes):
                if not triggered:
                    print("🎙️ Speech detected, recording...")
                    triggered = True
                voiced_frames.append(frame_bytes)
                silence_start = None
            elif triggered:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > silence_timeout:
                    print("🛑 Silence timeout reached, ending sentence.")
                    break

    return b''.join(voiced_frames)

def save_temp_wav(audio_bytes):
    filename = os.path.join(os.getcwd(), f"sentence_{uuid.uuid4().hex}.wav")
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio_bytes)
    return filename

def transcribe_live_sentences():
    root, text_widget = create_subtitle_window()

    def update_loop():
        try:
            audio_bytes = record_until_silence()
            if not audio_bytes:
                root.after(100, update_loop)
                return

            wav_path = save_temp_wav(audio_bytes)

            result = model.transcribe(wav_path, language=TARGET_LANGUAGE, fp16=False)
            text = result["text"].strip()
            text_en = translate_japanese_to_english(text)
            furigana_text = annotate_with_furigana(text)

            # Append text to the window
            text_widget.config(state=tk.NORMAL)
            text_widget.insert(tk.END, f"📝 {furigana_text}\n\n")
            text_widget.insert(tk.END, f"{furigana_text}\n→ {text_en}\n\n" )
            text_widget.see(tk.END)
            text_widget.config(state=tk.DISABLED)

            os.remove(wav_path)
            root.after(100, update_loop)
        except KeyboardInterrupt:
            root.destroy()

    root.after(100, update_loop)
    root.mainloop()


if __name__ == "__main__":
    transcribe_live_sentences()
