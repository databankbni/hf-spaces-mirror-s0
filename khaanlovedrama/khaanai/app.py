import gradio as gr
import re
from curl_cffi import requests

def resolve_byse_filemoon(video_id):
    if not video_id: return "Fadlan geli Video ID"
    
    # URL-ka dhabta ah ee Byse/Filemoon
    url = f"https://bysetayico.com/d/{video_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://q8y5z.com/", # Referer-kii aad sawirka ka soo qaaday
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

    try:
        # Isticmaal impersonate='chrome110' si looga gudbo xannibaadda
        response = requests.get(url, headers=headers, impersonate="chrome110", timeout=15)
        
        if response.status_code != 200:
            return f"Cilad: Server-ka Byse wuxuu soo celiyay Error {response.status_code}"

        html = response.text

        # 1. Raadi link-ga master.m3u8 (oo u qoran qaab JavaScript ah)
        # Waxaan raadinaynaa master.m3u8 oo wata dhamaan Token-yada t=..., s=..., e=...
        regex_hls = r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']'
        matches = re.findall(regex_hls, html)

        if matches:
            for link in matches:
                if "master.m3u8" in link:
                    final_link = link.replace("\\", "")
                    return final_link

        # 2. Haddii koodhku qarsoon yahay (Packed JavaScript), raadi xarfaha u dambeeya link-ga
        if "eval(function(p,a,c,k,e,d)" in html:
            return "Link-gu wuxuu ku jiraa koodh aad u qarsoon (Packed JS). Hugging Face ma awoodo inuu hadda furfuro."

        return "Link-gii master.m3u8 lama helin. Vidmoly/Filemoon ayaa laga yaabaa inay xannibtay Server-ka."

    except Exception as e:
        return f"Cilad farsamo: {str(e)}"

# Gradio Setup
with gr.Blocks() as demo:
    gr.Markdown("# Byse/Filemoon HLS Resolver")
    id_input = gr.Textbox(label="Geli Video ID (Tusaale: a86gqolnlygf)")
    output = gr.Textbox(label="Link-ga HLS ee rasmiga ah")
    btn = gr.Button("Soo saar Link-ga")
    btn.click(resolve_byse_filemoon, inputs=id_input, outputs=output)

demo.launch()