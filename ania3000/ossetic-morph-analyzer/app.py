from transformers import AutoModelForTokenClassification, AutoTokenizer
import numpy as np
import scipy.special
import torch
import torch.nn as nn
import torch.nn.functional as F
import gradio as gr
from torch.utils.data import Dataset
import re

class BiLSTMCharTagger(nn.Module):
    def __init__(self, vocab_size, embedding_dim, hidden_dim, output_dim):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        self.lstm = nn.LSTM(
            embedding_dim,
            hidden_dim,
            num_layers=1,
            bidirectional=True,
            batch_first=True
        )
        self.fc = nn.Linear(hidden_dim * 2, output_dim)

    def forward(self, text):
        embedded = self.embedding(text)
        lstm_out, _ = self.lstm(embedded)
        logits = self.fc(lstm_out)
        return logits

class WordSegmenterDecoder:
    def __init__(self, label_list):
        self.target_symbols_ = label_list
        self.target_symbol_codes_ = {sym: i for i, sym in enumerate(self.target_symbols_)}
        self.target_symbols_number_ = len(self.target_symbols_)

    def get_possible_next_states(self, prev_state_code):
        prev_label = self.target_symbols_[prev_state_code]
        START_LABELS = ["B", "S", "A", "N", "Z", "Y"]
        if prev_label in ["B", "A", "N", "Z", "Y"]:
            next_labels = ["I", "E"]
        elif prev_label == "I":
            next_labels = ["I", "E"]
        elif prev_label in ["E", "S", "X", "O"]:
            next_labels = START_LABELS + ["X", "O"]
        else:
            next_labels = []
        return [self.target_symbol_codes_[lbl] for lbl in next_labels if lbl in self.target_symbol_codes_]

    def is_correct_sequence(self, labels):
        if not labels: return False
        if labels[0] in ["I", "E"]: return False
        if labels[-1] not in ["E", "S", "X", "O"]: return False
        for i in range(len(labels) - 1):
            curr_code = self.target_symbol_codes_[labels[i]]
            next_code = self.target_symbol_codes_[labels[i+1]]
            if next_code not in self.get_possible_next_states(curr_code):
                return False
        return True

    def decode_best(self, probs, length):
        best_states = np.argmax(probs[:length], axis=1)
        best_labels = [self.target_symbols_[state_index] for state_index in best_states]
        if self.is_correct_sequence(best_labels):
            return best_states.tolist()
        costs, states = [], []
        first_step_costs = [np.inf] * self.target_symbols_number_
        first_step_states = [None] * self.target_symbols_number_
        valid_start_labels = ["B", "S", "A", "N", "Z", "Y", "X", "O"]
        for lbl in valid_start_labels:
            if lbl in self.target_symbol_codes_:
                idx = self.target_symbol_codes_[lbl]
                first_step_costs[idx] = -np.log(probs[0, idx] + 1e-12)
                first_step_states[idx] = idx
        costs.append(first_step_costs)
        states.append(first_step_states)
        for i in range(1, length):
            state_order = np.argsort(costs[-1])
            curr_costs = [np.inf] * self.target_symbols_number_
            prev_states = [None] * self.target_symbols_number_
            for prev_state in state_order:
                if np.isinf(costs[-1][prev_state]): break
                possible_states = self.get_possible_next_states(prev_state)
                for state in possible_states:
                    if np.isinf(curr_costs[state]):
                        curr_costs[state] = costs[-1][prev_state] - np.log(probs[i, state] + 1e-12)
                        prev_states[state] = prev_state
            costs.append(curr_costs)
            states.append(prev_states)
        possible_final_labels = ["E", "S", "X", "O"]
        possible_final_states = [self.target_symbol_codes_[lbl] for lbl in possible_final_labels if lbl in self.target_symbol_codes_]
        best_states_path = [min(possible_final_states, key=(lambda x: costs[-1][x]))]
        for j in range(length - 1, 0, -1):
            best_states_path.append(states[j][best_states_path[-1]])
        return best_states_path[::-1]

    def labels_to_words(self, input_string, labels):
        tokens = []
        curr_token = ""
        for letter, label in zip(input_string, labels):
            if label == "O":
                if curr_token: tokens.append(curr_token); curr_token = ""
                continue
            elif label == "A":
                if curr_token: tokens.append(curr_token)
                curr_token = "æ" + letter
            elif label == "N":
                if curr_token: tokens.append(curr_token)
                curr_token = "и" + letter
            elif label == "Z":
                if curr_token: tokens.append(curr_token)
                curr_token = "ц"
            elif label == "Y":
                if curr_token: tokens.append(curr_token)
                curr_token = "и"
            elif label == "B":
                if curr_token: tokens.append(curr_token)
                curr_token = letter
            elif label == "S":
                if curr_token: tokens.append(curr_token)
                tokens.append(letter); curr_token = ""
            elif label in ["I", "E"]:
                curr_token += letter
                if label == "E": tokens.append(curr_token); curr_token = ""
            elif label == "X":
                if curr_token: tokens.append(curr_token); curr_token = ""
        if curr_token: tokens.append(curr_token)
        return tokens

def rule_tokenize(sentences):
    punct = r'[!(),.:?‘’…]' # - – — «» " учесть цифры 50,8
    processed = []

    for sentence in sentences:
        sentence = re.sub(f"({punct})", r" \1 ", sentence)
        sentence = re.sub(r"\s+", " ", sentence)
        sentence = sentence.strip()

        sentence = re.sub(r"(У|у)(ӕд|æд)(дӕр|дæр)", r"\1\2 \3", sentence)
        sentence = re.sub(r"(Æ|Ӕ|ӕ|æ)(ппын)(дӕр|дæр)", r"\1\2 \3", sentence)
        sentence = re.sub(r"(Бынтон|бынтон)(дӕр|дæр)", r"\1 \2", sentence)
        sentence = re.sub(r"(Æ|Ӕ|ӕ|æ)(рмӕст|рмæст)(дӕр|дæр)", r"\1\2 \3", sentence)

        sentence = re.sub(r"(\w)(тӕккӕ|тæккæ)\b", r"\1 \2", sentence)
        sentence = re.sub(r"(\w)(нымӕр|нымæр)", r"\1 \2", sentence)
        sentence = re.sub(r"(\w)(мидӕг|мидæг)", r"\1 \2", sentence)
        sentence = re.sub(r"(\w)(фæстæ|фæстæ)", r"\1 \2", sentence)

        sentence = re.sub(r"(\w)(-|–|—)(иу|ма)", r"\1 \2 \3", sentence)

        sentence = re.sub(r"(К|к)(уы)(н)(нӕ|нæ)", r"\1\2д \4", sentence)
        sentence = re.sub(r"(Ц|ц)(ӕуы|æуы)(н)(нӕ|нæ)", r"\1\2л \4", sentence)

        sentence = re.sub(r"(У|у)(ыд)(ӕ|æ)(тт)(едт)(ӕ|æ)", r"\1\2он т\5\6", sentence)
        sentence = re.sub(r"(\w)(тт)(едт)(ӕ|æ)", r"\1\2\4 т\3\4", sentence)

        processed.append(sentence)
    return processed

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

checkpoint = torch.load("word_segmenter_bundle.pth", map_location=torch.device('cpu'))
char2idx = checkpoint['char2idx']
LABEL_LIST = checkpoint['LABEL_LIST']
config = checkpoint['model_config']

lstm_model = BiLSTMCharTagger(
    vocab_size=len(char2idx),
    embedding_dim=config['embedding_dim'],
    hidden_dim=config['hidden_dim'],
    output_dim=len(LABEL_LIST)
).to(device)
lstm_model.load_state_dict(checkpoint['model_state_dict'])
lstm_model.eval()

segmenter_decoder = WordSegmenterDecoder(LABEL_LIST)

def run_lstm_segmentation(input_text):
    if not input_text.strip():
        return ""
    char_ids = [char2idx.get(c, char2idx["<UNK>"]) for c in input_text]
    input_tensor = torch.tensor([char_ids]).to(device)
    with torch.no_grad():
        logits = lstm_model(input_tensor)
        probabilities = F.softmax(logits, dim=-1).squeeze(0).cpu().numpy()
    pred_codes = segmenter_decoder.decode_best(probabilities, len(input_text))
    pred_labels = [LABEL_LIST[code] for code in pred_codes]
    segmented_words = segmenter_decoder.labels_to_words(input_text, pred_labels)
    return " ".join(segmented_words)

def make_last_subtoken_mask(mask, has_cls=True, has_eos=True):
    if has_cls: mask = mask[1:]
    if has_eos: mask = mask[:-1]
    is_last_word = list((first != second) for first, second in zip(mask[:-1], mask[1:])) + [True]
    if has_cls: is_last_word = [False] + is_last_word
    if has_eos: is_last_word.append(False)
    return is_last_word

class UDDataset(Dataset):
    def __init__(self, data, tokenizer, min_count=1, tags=None): 
        self.data = data
        self.tokenizer = tokenizer
        self.raw_labels = [item["labels"] for item in data if "labels" in item]
        if tags is None:
            tag_counts = Counter([tag for elem in data for tag in elem["labels"]])
            self.tags_ = ["<PAD>", "<UNK>"] + [x for x, count in tag_counts.items() if count >= min_count]
        else:
            self.tags_ = tags
        self.tag_indexes_ = {tag: i for i, tag in enumerate(self.tags_)}
        self.unk_index = 1
        self.ignore_index = -100
    def __len__(self): return len(self.data)
    def __getitem__(self, index):
        item = self.data[index]
        tokenization = self.tokenizer(item["words"], is_split_into_words=True)
        last_subtoken_mask = make_last_subtoken_mask(tokenization.word_ids())
        answer = {"input_ids": tokenization["input_ids"], 
                  "mask": last_subtoken_mask, 
                  "attention_mask": tokenization["attention_mask"]}
        if "labels" in item:
            labels = [self.tag_indexes_.get(tag, self.unk_index) for tag in item["labels"]]
            zero_labels = np.array([self.ignore_index] * len(tokenization["input_ids"]), dtype=int)
            zero_labels[last_subtoken_mask] = labels
            answer["labels"] = zero_labels
        return answer

model_name = "ossetic-encoders/ossbert-morph-v2"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForTokenClassification.from_pretrained(model_name)
id2label = model.config.id2label
classes = [id2label[i] for i in range(len(id2label))]

model_name_l = "ossetic-encoders/ossbert-lemm-v2"
tokenizer_l = AutoTokenizer.from_pretrained(model_name_l)
model_l = AutoModelForTokenClassification.from_pretrained(model_name_l)
id2label_l = model_l.config.id2label
classes_l = [id2label_l[i] for i in range(len(id2label_l))]

def predict_top_k(model, dataset, classes, top_k):
    model.eval()
    answer = []
    with torch.no_grad():
        for elem in dataset:
            input_ids = torch.tensor(elem["input_ids"]).unsqueeze(0)
            attention_mask = torch.tensor(elem["attention_mask"]).unsqueeze(0)
            inputs = {"input_ids": input_ids, "attention_mask": attention_mask}
            outputs = model(**inputs)
            logits = outputs.logits.squeeze().numpy()
            mask = elem["mask"]
            probs = scipy.special.softmax(logits, axis=-1)[:len(mask)]
            top_k_indices = np.argsort(probs, axis=-1)[:, -top_k:][:, ::-1] 
            top_k_probs = np.take_along_axis(probs, top_k_indices, axis=-1)
            top_k_labels = []
            for i in range(len(mask)):
                if mask[i]:
                    labels = [classes[idx] for idx in top_k_indices[i]]
                    probs = [f"{p:.2f}" for p in top_k_probs[i]]
                    top_k_labels.append([(label, prob) for label, prob in zip(labels, probs)])
            answer.append({"top_k_labels": top_k_labels})
    return answer

def restore_lemma(word_form, label):
    suppl = {'æм1+уый#1+æм':'уый','и1+уæвын#1+и':'уæвын','ис1+уæвын#1+ис':'уæвын','кæй1+чи#1+кæй':'чи','кæм1+чи#1+кæм':'чи','кæмæ1+чи#1+кæмæ':'чи','кæмæй1+чи#1+кæмæй':'чи','кæмæн1+чи#1+кæмæн':'чи','кæмыты1+чи#1+кæмыты':'чи','кæуыл1+чи#1+кæуыл':'чи','мыл1+æз#1+мыл':'æз','мын1+æз#1+мын':'æз','нæ1+мах#1+нæ':'мах','ныл1+мах#1+ныл':'мах','нын1+мах#1+нын':'мах','сæ1+уыдон#1+сæ':'уыдон','сæм1+уыдон#1+сæм':'уыдон','семæ1+уыдон#1+семæ':'уыдон','уæ1+сымах#1+уæ':'сымах'}
    try:
        lemma_rule, form_rule = label.split('#')
        form_parts = form_rule.split('+')
        extracted_vars = {}
        regex_pattern = ""
        var_order = []
        for part in form_parts:
            if part.isdigit():
                regex_pattern += r"(.+)"
                var_order.append(int(part))
            else:
                regex_pattern += re.escape(part)
        match = re.match(f"^{regex_pattern}$", word_form)
        if match: 
            extracted_vars = {var_num: val for var_num, val in zip(var_order, match.groups())}
        else:
            match = re.match(f"^{regex_pattern}$", word_form.lower())
            if match:
                extracted_vars = {var_num: val for var_num, val in zip(var_order, match.groups())}
            else:
                if word_form+label in suppl: return suppl[word_form+label]
                else: return word_form
        lemma_parts = lemma_rule.split('+')
        final_lemma_pieces = []
        for part in lemma_parts:
            if part.isdigit():
                var_num = int(part)
                final_lemma_pieces.append(extracted_vars.get(var_num, ""))
            else:
                final_lemma_pieces.append(part)
        return "".join(final_lemma_pieces)
    except Exception:
        return word_form

def analyze_text(text, top_k_lemmas, top_k_tags, show_paradigm, show_subtokens):
    text = text.replace('Ӕ', 'Æ').replace('ӕ', 'æ')
    text = rule_tokenize([text])[0]
    text = run_lstm_segmentation(text)
    
    data_sample = {"words": text.split()}
    
    # if not data_sample["words"]:
    #     return "Входной текст пуст или не удалось распознать слова."
        
    test_dataset = UDDataset([data_sample], tokenizer, tags=classes)
    tag_predictions = predict_top_k(model, test_dataset, classes, top_k=top_k_tags)
    
    test_dataset_l = UDDataset([data_sample], tokenizer_l, tags=classes_l)
    lemma_predictions = predict_top_k(model_l, test_dataset_l, classes_l, top_k=top_k_lemmas)
    
    result = []
    #result.append(f"[Final Processed Text]: {text}\n" + "="*30 + "\n")
        
    counter = 1
    for word, tag_options, lemma_options in zip(
        data_sample["words"],
        tag_predictions[0]["top_k_labels"],
        lemma_predictions[0]["top_k_labels"]
    ):
        tag_str = ", ".join([f"{label} ({100*float(prob):.2f}%)" for label, prob in tag_options])
        lemma_str = ", ".join([f"{restore_lemma(word, label)} ({100*float(prob):.2f}%)" for label, prob in lemma_options])
        paradigm_str = ", ".join([f"{label} ({100*float(prob):.2f}%)" for label, prob in lemma_options])
        
        line = f"{counter}. Form: {word}"
        if show_subtokens == "Yes":
            line += f"\nSubtokens: {' '.join(tokenizer.tokenize(word))}"
        if show_paradigm == "Yes":
            line += f"\nParadigm: {paradigm_str}"
        line += f"\nLemma: {lemma_str}"
        line += f"\nTag: {tag_str}"
        result.append(line)
        result.append("")
        counter += 1
        
    return "\n".join(result).strip()

demo = gr.Interface(
    fn=analyze_text,
    inputs=[
        gr.Textbox(label="Input sentence", placeholder="Insert raw sentence here..."),
        gr.Slider(minimum=1, maximum=5, value=1, step=1, label="Top-k for lemmas"),
        gr.Slider(minimum=1, maximum=5, value=1, step=1, label="Top-k for tags"),
        gr.Dropdown(choices=["Yes", "No"], value="No", label="Show abstract paradigm label"),
        gr.Dropdown(choices=["Yes", "No"], value="No", label="Show subword tokenization")
    ],
    outputs=gr.Textbox(label="Analysis in UD v2"),
    title="In-context morphological analyzer for Ossetic",
    description="Insert raw sentence in Ossetic and receive POS, morphological features and lemmas in UD v2."
)

demo.launch(ssr_mode=False, theme=gr.themes.Base())