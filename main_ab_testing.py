import itertools
import gradio as gr
from openai import OpenAI
from env_vars import *

api_key = OPENAI_API_KEY
oai_model_name = "gpt-3.5-turbo"
left_system_prompt = "You are helpful AI."
right_system_prompt = "As a top-tier Python Software Engineer, prioritize concise, clear, and comprehensive communication. Be direct and detailed, optimizing your code for both readability and efficiency. Follow best practices to create minimal, effective lines of code. Apply these principles to elevate your programming skills."
oai_client = OpenAI(api_key=api_key)
text_size = gr.themes.sizes.text_md
block_css = "block_css.css"
notice_markdown = """## Chat and Compare
- We're excited to present a comparison of two Ansari versions.
- Engage with the two anonymized versions by asking questions.
- Vote for your favorite response and continue chatting until you identify the winner.

## Let's Start!"""

def handle_chat(user_message, chat_history, side):
    system_prompt = left_system_prompt if side == "left" else right_system_prompt
    history_openai_format = [{"role": "system", "content": system_prompt }]
    for human, assistant in chat_history:
        history_openai_format.append({"role": "user", "content": human })
        history_openai_format.append({"role": "assistant", "content": assistant})
    history_openai_format.append({"role": "user", "content": user_message})

    response = oai_client.chat.completions.create(model=oai_model_name,
                                                  messages=history_openai_format,
                                                  temperature=1.0,
                                                  stream=True)

    return response


def handle_user_message(user_message, right_chat_history, left_chat_history):
    if not user_message.strip():
        yield user_message, right_chat_history, left_chat_history, *keep_unchanged_buttons()
    else:
        right_chat_response = handle_chat(user_message, right_chat_history, "right")
        left_chat_response = handle_chat(user_message, left_chat_history, "left")

        right_chat_history.append([user_message, ""])
        left_chat_history.append([user_message, ""])

        for right_chunk, left_chunk in itertools.zip_longest(right_chat_response, left_chat_response, fillvalue=None):
            if right_chunk:
                right_content = right_chunk.choices[0].delta.content
                if right_content:
                    right_chat_history[-1][1] += right_content
            if left_chunk:
                left_content = left_chunk.choices[0].delta.content
                if left_content:
                    left_chat_history[-1][1] += left_content

            yield "", right_chat_history, left_chat_history, *disable_buttons()
        yield "", right_chat_history, left_chat_history, *enable_buttons()

def regenerate(right_chat_history, left_chat_history):
    for result in handle_user_message(right_chat_history[-1][0], right_chat_history[:-1], left_chat_history[:-1]):
        yield result

def keep_unchanged_buttons():
    return tuple([gr.Button() for _ in range(6)])

def enable_buttons():
    return tuple([gr.Button(interactive=True, visible=True) for _ in range(6)])

def hide_buttons():
    return tuple([gr.Button(interactive=False, visible=False) for _ in range(6)])

def disable_buttons(count=6):
    return tuple([gr.Button(interactive=False, visible=True) for _ in range(count)])

def left_vote_last_response(right_chat_history, left_chat_history):
    print("left_vote_last_response")
    print(left_chat_history)
    return disable_buttons(4)

def right_vote_last_response(right_chat_history, left_chat_history):
    print("right_vote_last_response")
    print(right_chat_history)
    return disable_buttons(4)

def tie_vote_last_response(right_chat_history, left_chat_history):
    print("tie_vote_last_response")
    print(right_chat_history, left_chat_history)
    return disable_buttons(4)

def bothbad_vote_last_response(right_chat_history, left_chat_history):
    print("bothbad_vote_last_response")
    print(right_chat_history, left_chat_history)
    return disable_buttons(4)


def create_compare_performance_tab():
    with gr.Tab("Compare Performance", id=0):
        gr.Markdown(notice_markdown, elem_id="notice_markdown")
        # with gr.Group(elem_id="share-region-anony"):
        with gr.Row():
            
            with gr.Column():
                left_chat_dialog = gr.Chatbot(
                    label="Model A",
                    elem_id="chatbot",
                    height=550,
                    show_copy_button=True,
                )
            with gr.Column():
                right_chat_dialog = gr.Chatbot(
                    label="Model B",
                    elem_id="chatbot",
                    height=550,
                    show_copy_button=True,
                )
        with gr.Row():
            leftvote_btn = gr.Button(
                value="👈  A is better", visible=False, interactive=False
            )
            rightvote_btn = gr.Button(
                value="👉  B is better", visible=False, interactive=False
            )
            tie_btn = gr.Button(value="🤝  Tie", visible=False, interactive=False)
            bothbad_btn = gr.Button(
                value="👎  Both are bad", visible=False, interactive=False
            )

        with gr.Row():
            user_msg_textbox = gr.Textbox(
                show_label=False,
                placeholder="✏️ Enter your prompt and press ENTER ⏎",
                elem_id="input_box",
            )
            send_btn = gr.Button(value="Send", variant="primary", scale=0)

        with gr.Row():
            clear_btn = gr.Button(value="🌙 New Round", interactive=False)
            regenerate_btn = gr.Button(value="🔄 Regenerate", interactive=False)
        ##
        btn_list = [
            leftvote_btn,
            rightvote_btn,
            tie_btn,
            bothbad_btn,
            regenerate_btn,
            clear_btn,
        ]
        leftvote_btn.click(
            left_vote_last_response,
            [right_chat_dialog, left_chat_dialog],
            [leftvote_btn, rightvote_btn, tie_btn, bothbad_btn],
        )
        rightvote_btn.click(
            right_vote_last_response,
            [right_chat_dialog, left_chat_dialog],
            [leftvote_btn, rightvote_btn, tie_btn, bothbad_btn],
        )
        tie_btn.click(
            tie_vote_last_response,
            [right_chat_dialog, left_chat_dialog],
            [leftvote_btn, rightvote_btn, tie_btn, bothbad_btn],
        )
        bothbad_btn.click(
            bothbad_vote_last_response,
            [right_chat_dialog, left_chat_dialog],
            [leftvote_btn, rightvote_btn, tie_btn, bothbad_btn],
        )
        clear_btn.click(
            lambda: tuple([None] * 3 + [gr.Button(interactive=False, visible=True)]*6),
            None,
            [user_msg_textbox, right_chat_dialog, left_chat_dialog] + btn_list,
        )

        user_msg_textbox.submit(
            handle_user_message,
            [user_msg_textbox, right_chat_dialog, left_chat_dialog],
            [user_msg_textbox, right_chat_dialog, left_chat_dialog] + btn_list,
        )

        send_btn.click(
            handle_user_message,
            [user_msg_textbox, right_chat_dialog, left_chat_dialog],
            [user_msg_textbox, right_chat_dialog, left_chat_dialog] + btn_list,
        )

        regenerate_btn.click(
            regenerate, 
            [right_chat_dialog, left_chat_dialog],
            [user_msg_textbox, right_chat_dialog, left_chat_dialog] + btn_list
        )

def create_about_tab():
    with gr.Tab("🛈 About Us", id=1):
        about_markdown = "This UI is designed to test a change to Ansari's functionality before deployment"
        gr.Markdown(about_markdown, elem_id="about_markdown")

with gr.Blocks(
    title="Ansari Compare",
    theme=gr.themes.Soft(text_size=text_size,
                          primary_hue=gr.themes.colors.sky, secondary_hue=gr.themes.colors.blue),
    css=block_css,
) as gr_app:

    with gr.Tabs() as tabs:
        create_compare_performance_tab()
        create_about_tab()

if __name__ == "__main__":
    gr_app.queue(
            default_concurrency_limit=10,
            status_update_rate=10,
            api_open=False,
        ).launch(
            max_threads=200,
            show_api=False,
            share=False,
        )

