import json

conversations_file = "new_conversations.json"

conversations = json.load(open(conversations_file, "r", encoding="utf-8"))

meanings_mapping: dict[str, list[str]] = {}


def parse_message(message):
    parts = message["content"]["parts"]
    content = parts[0]
    return content


question_count = 0


def parse_conv(conv):
    chat_nodes = conv["mapping"]
    for node in chat_nodes.values():
        if message := node["message"]:
            role = message["author"]["role"]
            if role == "user":
                parts = message["content"]["parts"]
                question: str = parts[0]
                global question_count
                question_count = question_count + 1
                children_id = node["children"]
                answers = []
                for child_id in children_id:
                    child_node = chat_nodes[child_id]
                    if child_message := child_node["message"]:
                        answer = parse_message(child_message)
                        answers.append(answer)
                question = question.lower().strip()
                if old_answers := meanings_mapping.get(question.lower()):
                    old_answers.extend(answers)
                    old_answers[:] = list(set(old_answers))
                else:
                    meanings_mapping[question.lower()] = answers


for conv in conversations:
    parse_conv(conv)

print(question_count)
