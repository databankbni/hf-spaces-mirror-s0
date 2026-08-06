from typing import Any

def is_heading(block: dict[str, Any], block_type: str) -> bool:

    headings = [
        'heading_1',
        'heading_2',
        'heading_3',
        'heading_4',
    ]

    if block_type in headings:
        rich_text = block.get(block_type, {}).get('rich_text', [])
        return bool(rich_text)

    if block_type == 'paragraph':

        rich_text = block.get("paragraph", {}).get("rich_text", [])

        if not rich_text:
            return False

        text = ''.join(
            item.get('plain_text', '')
            for item in rich_text
        )

        is_bold = all(
            item.get('annotations', {}).get('bold', False)
            for item in rich_text
        )

        is_short = len(text.split()) <= 10

        if is_bold and is_short:
            return True

    return False


def parse_notion_text(blocks: list[dict]) -> list[dict[str, str]]:

    current_topic = ''
    last_topic = ''
    current_text = ''
    last_heading = False
    started = False
    chunks = []

    for block in blocks:

        block_type = block.get('type')

        if is_heading(block, block_type):

            if current_text.strip():
                chunks.append({
                    'topic': current_topic.strip(),
                    'text': current_text.strip()
                })
                last_topic = current_topic
                current_topic = ''
                current_text = ''
                started = True

            heading_data = block.get(block_type, {})

            text = ''.join(
                t.get('plain_text', '')
                for t in heading_data.get('rich_text', [])
            ).strip()

            if started and last_heading:
                current_topic = current_topic.split(' > ')[1].strip() + ' > ' + text.strip()
            else:
                if current_topic:
                    current_topic = current_topic.strip() + ' > ' + text.strip()
                else:
                    if last_topic:
                        current_topic = last_topic.split(' > ')[0].strip() + ' > ' + text.strip()
                    else:
                        current_topic = text.strip()

            last_heading = True


        if block_type == 'paragraph':

            last_heading = False

            text = ''.join(
                t['plain_text'] for t in block['paragraph']['rich_text']
            )

            if len(text.split()) <= 0:
                continue

            if not current_text:
                current_text = text.strip()
            else:
                current_text = current_text.strip() + '\n\n' + text.strip()

    if current_text.strip():
        chunks.append({
            'topic': current_topic.strip(),
            'text': current_text.strip()
        })

        return chunks

    



