from dotenv import load_dotenv
import os
import uuid
from datetime import timedelta
import textwrap

import google.generativeai as genai

from langchain_community.chat_message_histories import MomentoChatMessageHistory
from langchain.schema import HumanMessage, AIMessage

import flet as ft

import PIL.Image
from PIL import ImageGrab

from google.cloud import texttospeech
import pygame
import time

load_dotenv()

# init gemini
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
generation_config = genai.GenerationConfig(temperature=0.4)
model = genai.GenerativeModel(
    os.environ["GEMINI_API_MODEL"], generation_config=generation_config
)

# init text-to-speech, voice
pygame.mixer.init()
client = texttospeech.TextToSpeechClient()
voice = texttospeech.VoiceSelectionParams(
    language_code="	ja-JP",
    name="ja-JP-Standard-D",
    ssml_gender=texttospeech.SsmlVoiceGender.MALE,
)
audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

# init memonto, history
session_id = str(uuid.uuid4())
cache_name = "langchain"
history = MomentoChatMessageHistory.from_client_params(
    session_id,
    cache_name,
    timedelta(hours=int(os.environ["MOMENTO_TTL"])),
)


def format_chat_history(messages):
    formatted_history = ""
    for message in messages:
        if isinstance(message, HumanMessage):
            formatted_history += f"ユーザー: {message.content}\n"
        elif isinstance(message, AIMessage):
            formatted_history += f"あなた: {message.content}\n"
    return formatted_history


class Message:
    def __init__(self, user_name: str, text: str, message_type: str):
        self.user_name = user_name
        self.text = text
        self.message_type = message_type


class AIMessageControl(ft.Row):
    def __init__(self, message: Message):
        chat_history = format_chat_history(history.messages)

        ImageGrab.grab().quantize(256).save("screenshot.png")
        prompt = (
            textwrap.dedent("""
                あなたは優秀なAIエージェントです。入力: に続くユーザーからのテキスト対して150文字以内で回答してください。
                必要があれば、過去の会話を参照して回答してください。私達の過去の会話は以下のとおりです。
                ```
                {history}
                ```
                入力: {input}
            """)
            .format(history=chat_history, input=message.text)
            .strip()
        )
        print(prompt)
        response = model.generate_content([prompt, PIL.Image.open("./screenshot.png")])

        # 履歴に会話を追加
        history.add_message(HumanMessage(content=message.text))
        history.add_message(AIMessage(content=response.text))

        # 音声の作成
        input_text = texttospeech.SynthesisInput(text=response.text)
        speech_response = client.synthesize_speech(
            request={"input": input_text, "voice": voice, "audio_config": audio_config}
        )
        with open("voice.mp3", "wb") as out:
            out.write(speech_response.audio_content)

        super().__init__()
        self.vertical_alignment = ft.CrossAxisAlignment.START
        self.controls = [
            ft.CircleAvatar(
                content=ft.Text("AI"),
                color=ft.colors.WHITE,
                bgcolor=ft.colors.PURPLE,
            ),
            ft.Column(
                [
                    ft.Text(message.user_name),
                    ft.Text(response.text, selectable=True),
                ],
                tight=True,
                spacing=5,
                width=600,
            ),
        ]


class UserMessageControl(ft.Row):
    def __init__(self, message: Message):
        super().__init__()
        self.vertical_alignment = ft.CrossAxisAlignment.START
        self.controls = [
            ft.CircleAvatar(
                content=ft.Text("U"),
                color=ft.colors.WHITE,
                bgcolor=ft.colors.BLUE,
            ),
            ft.Column(
                [
                    ft.Text(message.user_name),
                    ft.Text(message.text, selectable=True),
                ],
                tight=True,
                spacing=5,
            ),
        ]


def main(page: ft.Page):
    page.title = "AI Chat"
    page.window_opacity = 0.9
    user_name = "User"
    message_type = "user_message"

    def send_prompt_to_ai(prompt):
        on_message(
            Message(
                "AI",
                prompt,
                "ai_message",
            )
        )
        # 音声再生
        pygame.mixer.music.load("./voice.mp3")
        voice_length = pygame.mixer.Sound("./voice.mp3").get_length()
        pygame.mixer.music.play()
        time.sleep(voice_length)
        pygame.mixer.music.stop()

    def send_prompt_click(e):
        if new_message.value == "":
            return

        on_message(
            Message(
                user_name,
                new_message.value,
                message_type,
            )
        )
        prompt = new_message.value
        new_message.value = ""
        new_message.focus()
        page.update()

        # ローディングの表示
        chat.controls.append(
            ft.Row([ft.ProgressRing(), ft.Text("Generate messages...")])
        )
        page.update()

        send_prompt_to_ai(prompt)
        prompt = ""

    def on_message(message: Message):
        if message.message_type == "user_message":
            m = UserMessageControl(message)
        elif message.message_type == "ai_message":
            m = AIMessageControl(message)
            # ローディングを削除する
            chat.controls.pop()

        chat.controls.append(m)
        page.update()

    # チャット欄
    chat = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=True,
    )

    # プロンプト入力フォーム
    new_message = ft.TextField(
        hint_text="Write a prompt...",
        autofocus=True,
        shift_enter=True,
        min_lines=1,
        max_lines=5,
        filled=True,
        expand=True,
        on_submit=send_prompt_click,
        border_radius=15,
        fill_color=ft.colors.BLACK12,
        border_color=ft.colors.WHITE30,
    )

    page.add(
        ft.Container(
            content=chat,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=5,
            padding=10,
            expand=True,
        ),
        ft.Row(
            [
                new_message,
                ft.IconButton(
                    icon=ft.icons.ARROW_CIRCLE_UP_OUTLINED,
                    tooltip="Send prompt",
                    on_click=send_prompt_click,
                    scale=1.5,
                ),
            ]
        ),
    )


ft.app(target=main)
