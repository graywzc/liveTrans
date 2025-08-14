import sounddevice as sd
import queue
import json
import threading
from vosk import Model, KaldiRecognizer
import tkinter as tk
from deep_translator import GoogleTranslator

# === CONFIG ===
MODEL_PATH = "model-ja"
SAMPLE_RATE = 16000

model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)
audio_queue = queue.Queue()

# Holds final transcript + translation
full_transcript = ""


from pykakasi import Kakasi

def add_furigana(text):
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




def audio_callback(indata, frames, time, status):
    if status:
        print(f"Audio status: {status}")
    audio_queue.put(bytes(indata))

def translate_japanese_to_english(text):
    try:
        translated = GoogleTranslator(source='ja', target='en').translate(text)
        return translated
    except Exception as e:
        return f"[Translation error: {e}]"

def start_audio_stream():
    global full_transcript
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000, dtype='int16',
                           channels=1, callback=audio_callback):
        print("Listening...")
        while True:
            data = audio_queue.get()
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                text_ja = result.get("text", "").strip()
                text_furigana = add_furigana(text_ja)
                if text_ja:
                    text_en = translate_japanese_to_english(text_ja)
                    full_transcript += f"{text_furigana}\n→ {text_en}\n\n"
                    render_full(full_transcript)
            else:
                partial = json.loads(recognizer.PartialResult())
                render_full(full_transcript + partial.get("partial", ""))

# === GUI Setup ===
def update_gui(text):
    output_text.configure(state='normal')
    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, text)
    output_text.see(tk.END)
    output_text.configure(state='disabled')



def _render_full(text: str):
    output_text.configure(state="normal")
    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, text)
    output_text.see(tk.END)
    output_text.configure(state="disabled")

def render_full(text: str):
    root.after(0, _render_full, text)

root = tk.Tk()
root.title("🎙️ Japanese Live Transcription + Translation")
root.geometry("1000x500")
root.configure(bg="black")

frame = tk.Frame(root, bg="black")
frame.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)

scrollbar = tk.Scrollbar(frame)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

output_text = tk.Text(frame, font=("Consolas", 18), fg="#00FF00", bg="black",
                      wrap=tk.WORD, yscrollcommand=scrollbar.set)
output_text.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

scrollbar.config(command=output_text.yview)
output_text.configure(state='disabled')


# Start the transcription thread
threading.Thread(target=start_audio_stream, daemon=True).start()

# Run the GUI loop
root.mainloop()
