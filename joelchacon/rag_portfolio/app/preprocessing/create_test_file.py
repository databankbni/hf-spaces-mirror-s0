def create_test_file(file_path: str):
    """
    Creates a .txt file with sample content for testing purposes.
    """
    sample_content = """
    Post 1: Introduction to AI Agents
    AI agents are programs designed to perform tasks autonomously. They can interact with their environment, make decisions, and learn from feedback.

    Post 2: Prompt Engineering Tips
    Prompt engineering is crucial for getting accurate responses from language models. Clear instructions and examples improve output quality.

    Post 3: Adversarial Attacks on LLMs
    Adversarial attacks can trick large language models into producing wrong or harmful outputs. Understanding vulnerabilities helps improve model safety.

    Post 4: Joel Chacon
    He is a friend of Raul a cat.
    """

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(sample_content.strip())

# Usage
create_test_file("test_file.txt")
print("Test file created: test_file.txt")

