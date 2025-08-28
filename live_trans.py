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
import threading, queue
ui_queue = queue.Queue()


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

def make_readonly(text):
    # Block typing, cut/paste, undo/redo
    def no_edit(_): return "break"
    for seq in ("<Key>", "<<Cut>>", "<<Paste>>", "<<Undo>>", "<<Redo>>"):
        text.bind(seq, no_edit)

    # Allow copy + select all on Win/Linux (Ctrl) and macOS (Cmd)
    text.bind("<Control-c>", lambda e: None)
    text.bind("<Command-c>", lambda e: None)
    text.bind("<Control-a>", lambda e: (text.tag_add("sel", "1.0", "end-1c"), "break"))
    text.bind("<Command-a>", lambda e: (text.tag_add("sel", "1.0", "end-1c"), "break"))

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
    make_readonly(text_widget)

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

    stop_event = threading.Event()
    threading.Thread(target=worker_loop, args=(stop_event,), daemon=True).start()

    def update_loop():
        # Drain anything the worker produced
        try:
            while True:
                block = ui_queue.get_nowait()
                text_widget.insert(tk.END, block)
                text_widget.see(tk.END)
        except queue.Empty:
            pass
        root.after(50, update_loop)  # keep UI responsive

    def on_close():
        stop_event.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    update_loop()
    root.mainloop()

def worker_loop(stop_event):
    while not stop_event.is_set():
        audio_bytes = record_until_silence()
        if not audio_bytes:
            continue

        wav_path = save_temp_wav(audio_bytes)
        try:
            result = model.transcribe(wav_path, language=TARGET_LANGUAGE, fp16=False)
            text = result["text"].strip()
            text_en = translate_japanese_to_english(text)
            furigana_text = annotate_with_furigana(text)
            block = f"📝 {furigana_text}\n→ {text_en}\n\n"
            ui_queue.put(block)  # hand off to UI thread
        finally:
            try: os.remove(wav_path)
            except OSError: pass



if __name__ == "__main__":
    transcribe_live_sentences()
