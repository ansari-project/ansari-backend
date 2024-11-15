import copy
import uuid

import gradio as gr

CSS = """
.contain { display: flex; flex-direction: column; }
#component-0 { height: 100%; flex-grow: 1; }
#chatbot { flex-grow: 1; overflow: auto;}
"""


class GradioPresenter:
    def __init__(self, agent, app_name, favicon_path):
        self.agent = agent
        self.app_name = app_name
        self.favicon_path = favicon_path

    def present(self):
        self.instances = {}
        self.histories = {}

        def generate_session_id():
            return str(f"{uuid.uuid4()}")

        def append_flag(msg):
            msg = msg + "Please flag this. "

        def clear_contents(msg):
            return ""

        with gr.Blocks(title=self.app_name, css=CSS) as app:
            # Note: Gradio Presenter is incredibly confusing.
            # We can't pass agents because they are not serializable.
            # instead what we do is that we maintain a dictionary of
            # LangChainChatAgents by uuid.
            my_uuid = gr.State(generate_session_id)

            chatbot = gr.Chatbot(
                [["", self.agent.greet()]],
                elem_id="chatbot",
                line_breaks=True,
            )
            msg = gr.Textbox(show_label=False, scale=10)
            with gr.Row():
                clr = gr.Button(
                    value="Clear",
                    size="sm",
                    scale=1,
                    variant="secondary",
                    elem_id="clr",
                )
                btn = gr.Button(
                    value="Send",
                    size="sm",
                    scale=2,
                    variant="primary",
                    elem_id="btn",
                )

            def user(user_message, history, my_uuid):
                if self.instances.get(my_uuid) is None:
                    self.instances[my_uuid] = copy.deepcopy(self.agent)
                    self.instances[my_uuid].session_tag = f"ses_{my_uuid}"
                    self.histories[my_uuid] = [["", self.agent.greet()]]
                self.histories[my_uuid].append([user_message, None])
                print("history is ", self.histories[my_uuid])
                return "", self.histories[my_uuid], my_uuid

            def bot(history, my_uuid):
                # Check if we've seen this uuid before. If not, greet then add to instances
                if self.instances.get(my_uuid) is None:
                    self.instances[my_uuid] = copy.deepcopy(self.agent)
                    self.instances[my_uuid].session_tag = f"ses_{my_uuid}"
                    self.histories[my_uuid] = [["", self.agent.greet()]]
                instance = self.instances[my_uuid]
                history = self.histories[my_uuid]

                history[-1][1] = ""
                print(f"history is {history}")
                for word in instance.process_input(history[-1][0]):
                    if word is None:
                        continue
                    history[-1][1] += word
                    yield history, my_uuid

            msg.submit(
                fn=user,
                inputs=[msg, chatbot, my_uuid],
                outputs=[msg, chatbot, my_uuid],
                queue=False,
            ).then(fn=bot, inputs=[chatbot, my_uuid], outputs=[chatbot, my_uuid])

            # Clicking on the button does the same thing as submitting.
            btn.click(
                fn=user,
                inputs=[msg, chatbot, my_uuid],
                outputs=[msg, chatbot, my_uuid],
                queue=False,
            ).then(fn=bot, inputs=[chatbot, my_uuid], outputs=[chatbot, my_uuid])

            clr.click(fn=clear_contents, inputs=[msg], outputs=[msg], queue=False)

        if self.favicon_path:
            app.launch(favicon_path=self.favicon_path)
        else:
            app.launch()
