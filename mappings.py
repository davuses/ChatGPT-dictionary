import json


def parse_message(message):
    parts = message["content"]["parts"]
    content = parts[0]
    return content


def parse_conv(conv, meanings_mapping):
    question_count = 0
    chat_nodes = conv["mapping"]
    for node in chat_nodes.values():
        if message := node["message"]:
            role = message["author"]["role"]
            if role == "user":
                parts = message["content"]["parts"]
                question: str = parts[0]
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
    print(question_count)


def get_question_answer_mappings(file="new_conversations.json"):
    conversations_file = file

    conversations = json.load(open(conversations_file, "r", encoding="utf-8"))

    question_answer_mappings: dict[str, list[str]] = {}
    for conv in conversations:
        parse_conv(conv, question_answer_mappings)

    return question_answer_mappings
