"""Run once at build time to cache MoLFormer weights into the repo."""
from transformers import AutoModel, AutoTokenizer
import os

cache_dir = os.path.join(os.path.dirname(__file__), "molformer_cache")
os.makedirs(cache_dir, exist_ok=True)

print("Downloading MoLFormer-XL...")
AutoTokenizer.from_pretrained("ibm/MoLFormer-XL-both-10pct",
                               trust_remote_code=True, cache_dir=cache_dir)
AutoModel.from_pretrained("ibm/MoLFormer-XL-both-10pct",
                           trust_remote_code=True, cache_dir=cache_dir)
print("Done.")