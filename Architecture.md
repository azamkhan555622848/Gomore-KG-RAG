0) What we’re building (one paragraph)

A FastAPI microservice that answers questions by: (1) retrieving many candidate passages with a dense retriever (we’ll use EmbeddingGemma-300M for vectors + FAISS/HNSW index), (2) building a per-query passage graph via entity linking to Wikidata and connecting passages whose entities are KG-adjacent, (3) running a Stage-1 GNN reranker over that graph to prune to 
𝑁
1
N
1
	​

, (4) encoding each 
(
𝑄
⊕
𝑝
𝑖
)
(Q⊕p
i
	​

) with a small FiD reader (T5-Small), tapping an intermediate encoder layer to run Stage-2 GNN and prune to 
𝑁
2
N
2
	​

, then (5) finishing the encoder for 
𝑁
2
N
2
	​

 and decoding the answer. This follows FiD and KG-FiD exactly, plus the FiDO efficiency insight that decoding bandwidth dominates so pruning/early-exit helps. 
arXiv
+3
arXiv
+3
aclanthology.org
+3

1) Stack & dependencies

Retriever (dense): Google EmbeddingGemma-300M (multilingual, designed for on-device/edge; perfect embeddings for RAG). 
Google AI for Developers
+2
developers.googleblog.com
+2

ANN index: FAISS (GPU/CPU; IVF-PQ/HNSW). Use USearch if you prefer a tiny dependency, but FAISS is the standard. 
faiss.ai
+2
GitHub
+2

(Optional) BM25 hybrid: Pyserini (Lucene). 
GitHub
+1

Entity linking (EL): BLINK or REL (Python packages/APIs). 
GitHub
+2
GitHub
+2

KG source: Wikidata weekly dumps (title→QID + edges) and/or WDQS SPARQL with caching. 
wikidata.org
+3
wikidata.org
+3
qwikidata.readthedocs.io
+3

GNN: PyTorch Geometric (GAT/GATv2/R-GCN). 
pytorch-geometric.readthedocs.io
+1

Reader (FiD): T5-Small via Hugging Face Transformers, exposed with output_hidden_states=True. 
huggingface.co
+1

API: FastAPI + Uvicorn. 
fastapi.tiangolo.com
+1

pip install "transformers>=4.44" accelerate torch torchvision torchaudio
pip install faiss-gpu  # or faiss-cpu
pip install pyserini usearch  # (optional: one or both)
pip install torch-geometric  # follow PyG install selector for your CUDA
pip install fastapi uvicorn
pip install git+https://github.com/facebookresearch/BLINK.git  # or: pip install rel-nlp

2) Repo layout (monorepo-friendly)
graph_rag/
  configs/
    kgfid_mobile.yaml
  data/
    passages.jsonl         # id, title, text, url
    title2qid.sqlite       # Wikipedia title -> Wikidata QID
    kg_edges.sqlite        # light neighbor store (QID pairs, relation, weight)
    faiss_index/           # FAISS files
  retriever/
    build_index.py
    dense.py               # EmbeddingGemma encoder + FAISS wrapper
    hybrid.py              # (optional) Pyserini BM25 fusion
  el/
    title2qid.py           # sitelinks/dump -> sqlite
    blink_rel.py           # optional mention-level EL
  kg/
    edges.py               # load neighbors from sqlite / cached SPARQL
  graph/
    stage1_gnn.py          # GAT/R-GCN reranker
    stage2_gnn.py
    build_graph.py         # construct passage graph for a query
  fid/
    reader.py              # T5-Small FiD wrapper
    pruning.py             # token-pruning utilities
  service/
    api.py                 # FastAPI app
    pipeline.py            # end-to-end KG-FiD pipeline

3) Config (example)
retriever:
  model: google/embeddinggemma-300m   # HF id
  dim: 1024
  topN0: 600
  faiss:
    type: hnsw
    m: 32
    ef_search: 80
hybrid:
  use_bm25: false
graph:
  edge_weight_threshold: 0.3
  typed_edges: true
gnn:
  stage1: {type: gat, layers: 2, hidden: 256, heads: 4, dropout: 0.1}
  stage2: {type: gat, layers: 2, hidden: 256, heads: 4, dropout: 0.1}
reader:
  model: google-t5/t5-small
  max_q_len: 32
  max_p_len: 160
  enc_tap_layer: 5          # L1 for Stage-2 pruning
  N1: 80
  N2: 12
  token_prune_k: 96
server:
  batch_size: 1
  device: cuda


EmbeddingGemma details and prompts are on HF/Google docs; T5-Small is ~60M params and runs well on a single GPU/CPU. 
huggingface.co
+2
Google AI for Developers
+2

4) Core pipeline (Python skeletons)
4.1 Retriever (EmbeddingGemma + FAISS)
# retriever/dense.py
import faiss, torch
from transformers import AutoModel, AutoTokenizer

class DenseRetriever:
    def __init__(self, model_id, faiss_index_path, device="cuda"):
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id).to(device).eval()
        self.device = device
        self.index = faiss.read_index(faiss_index_path)  # IVF/HNSW/etc.
    @torch.inference_mode()
    def embed(self, text: str) -> torch.Tensor:
        x = self.tok(text, return_tensors="pt", truncation=True, max_length=256).to(self.device)
        # EmbeddingGemma uses the last hidden state pooled; check model card for best practice
        out = self.model(**x)
        emb = out.last_hidden_state[:, 0]  # or mean-pool
        return torch.nn.functional.normalize(emb, dim=-1).squeeze(0).float().cpu().numpy()
    def search(self, q: str, topk=600):
        qv = self.embed(q)
        D, I = self.index.search(qv[None, :], topk)
        return I[0].tolist(), D[0].tolist()


FAISS is the standard dense ANN stack for RAG; EmbeddingGemma is a 308M param emb model tuned for on-device/edge & RAG embeddings. 
huggingface.co
+3
faiss.ai
+3
GitHub
+3

4.2 Build the passage graph (entities & edges)
# graph/build_graph.py
import networkx as nx

def build_passage_graph(passages, title2qid_db, kg_edges_db, edge_thresh=0.3):
    """
    passages: list of dicts {id, title, text, score}
    Map titles -> QIDs, add edges if entities are KG-adjacent. Weight by EL confidence or 1.0 at title-level.
    """
    G = nx.Graph()
    for p in passages:
        qid = title2qid_db.get(p["title"])  # article-level EL via sitelinks
        if not qid: continue
        G.add_node(p["id"], qid=qid, score=p["score"])
    nodes = list(G.nodes())
    for i in range(len(nodes)):
        for j in range(i+1, len(nodes)):
            qi, qj = G.nodes[nodes[i]]["qid"], G.nodes[nodes[j]]["qid"]
            w = kg_edges_db.weight(qi, qj)  # typed edge weight / PPR / 1-hop
            if w and w >= edge_thresh:
                G.add_edge(nodes[i], nodes[j], weight=w)
    return G


Use Wikidata sitelinks (title→QID) and neighbors from dumps/WDQS; KG-FiD connects retrieved passages if their entities are linked, then GNN-reranks. 
ar5iv
+3
wikidata.org
+3
qwikidata.readthedocs.io
+3

4.3 Stage-1 GNN reranker (PyG GAT)
# graph/stage1_gnn.py
import torch, torch.nn.functional as F
from torch_geometric.nn import GATConv

class Stage1GAT(torch.nn.Module):
    def __init__(self, d_in=1024, hidden=256, heads=4, layers=2, dropout=0.1):
        super().__init__()
        self.gats = torch.nn.ModuleList()
        self.gats.append(GATConv(d_in, hidden, heads=heads, dropout=dropout))
        for _ in range(layers-1):
            self.gats.append(GATConv(hidden*heads, hidden, heads=1, dropout=dropout, concat=False))
        self.scorer = torch.nn.Linear(hidden, 1)
    def forward(self, x, edge_index, edge_weight=None):
        h = x
        for gat in self.gats:
            h = F.elu(gat(h, edge_index, edge_weight))
        return self.scorer(h).squeeze(-1)


GAT/GATv2 are standard in PyG; you’ll feed node features = passage embeddings (from the retriever). 
pytorch-geometric.readthedocs.io
+1

4.4 FiD reader (T5-Small) with Stage-2 pruning
# fid/reader.py
import torch
from transformers import T5ForConditionalGeneration, T5TokenizerFast

class FiDReader:
    def __init__(self, model_id="google-t5/t5-small", device="cuda"):
        self.tok = T5TokenizerFast.from_pretrained(model_id)
        self.model = T5ForConditionalGeneration.from_pretrained(
            model_id, output_hidden_states=True
        ).to(device).eval()
        self.device = device

    @torch.inference_mode()
    def encode_to_layer(self, question, passages, layer_idx=5, max_q=32, max_p=160):
        # encode each (Q ⊕ passage) independently (FiD)
        enc_states_per_passage = []
        for p in passages:
            s = f"question: {question} context: {p['text']}"
            x = self.tok(s, return_tensors="pt", truncation=True,
                         max_length=max_q+max_p).to(self.device)
            out = self.model.encoder(**x, output_hidden_states=True, return_dict=True)
            # pool tokens from intermediate layer
            h = out.hidden_states[layer_idx].mean(dim=1)  # [B, d]
            enc_states_per_passage.append((p["id"], h.squeeze(0)))
        return enc_states_per_passage

    @torch.inference_mode()
    def generate(self, question, passages, max_new_tokens=32):
        # Concatenate encoder tokens of selected passages (standard FiD impl would collect token states)
        batch_inputs = [f"question: {question} context: {p['text']}" for p in passages]
        x = self.tok(batch_inputs, padding=True, truncation=True,
                     max_length=192, return_tensors="pt").to(self.device)
        out = self.model.generate(**x, max_new_tokens=max_new_tokens)
        return self.tok.decode(out[0], skip_special_tokens=True)


This reflects FiD’s “encode each passage separately; fuse in the decoder”, and the KG-FiD trick to tap an intermediate encoder layer for the Stage-2 graph rerank (so you can stop encoding pruned passages). 
arXiv
+1

4.5 Stage-2 GNN + pruning
# graph/stage2_gnn.py
# Same architecture as Stage1GAT; node feats now = pooled encoder states from layer L1.
# Return top-N2 ids, then finish encoder+decode only for those passages.

4.6 End-to-end pipeline + FastAPI
# service/pipeline.py
from retriever.dense import DenseRetriever
from graph.build_graph import build_passage_graph
from graph.stage1_gnn import Stage1GAT
from graph.stage2_gnn import Stage1GAT as Stage2GAT
from fid.reader import FiDReader

class KGFiDPipeline:
    def __init__(self, cfg):
        self.ret = DenseRetriever(cfg["retriever"]["model"], "data/faiss_index/index.faiss")
        self.reader = FiDReader(cfg["reader"]["model"])
        self.stage1 = Stage1GAT(d_in=cfg["retriever"]["dim"])
        self.stage2 = Stage2GAT(d_in=self.reader.model.config.d_model)
        # ...load weights if trained

    def answer(self, question: str):
        ids, scores = self.ret.search(question, topk=cfg["retriever"]["topN0"])
        passages = [load_passage(i, scores[k]) for k,i in enumerate(ids)]  # your store
        G = build_passage_graph(passages, title2qid_db, kg_edges_db, cfg["graph"]["edge_weight_threshold"])
        # Build PyG tensors (x from retriever embeddings, edge_index from G)
        x = get_emb_matrix(passages)  # [N0, d]
        edge_index, edge_weight = to_pyg(G)
        s1 = self.stage1(x, edge_index, edge_weight)
        topN1 = pick_topN(passages, s1, N=cfg["reader"]["N1"])

        # Encode to layer L1 and Stage-2 rerank
        enc_states = self.reader.encode_to_layer(question, topN1, layer_idx=cfg["reader"]["enc_tap_layer"])
        x2, edge_index2, edge_weight2 = pack_stage2(enc_states, G)
        s2 = self.stage2(x2, edge_index2, edge_weight2)
        topN2 = pick_topN(topN1, s2, N=cfg["reader"]["N2"])

        # Finish encoder & decode only for N2
        return self.reader.generate(question, topN2)

# service/api.py
from fastapi import FastAPI
from service.pipeline import KGFiDPipeline
import yaml
app = FastAPI(title="Graph-RAG (KG-FiD)")
cfg = yaml.safe_load(open("configs/kgfid_mobile.yaml"))
pipe = KGFiDPipeline(cfg)

@app.post("/answer")
def answer(q: str):
    out = pipe.answer(q)
    return {"answer": out}


FastAPI gives you OpenAPI/Swagger out of the box, easy to call from Flutter’s http/dio. 
fastapi.tiangolo.com

5) Pre-processing scripts you’ll run once

Split corpus to passages (≈100-word blocks) and store {id,title,text}. (Matches FiD practice.) 
arXiv

Build dense index: embed all passages with EmbeddingGemma → train/build FAISS (IVF-PQ/HNSW) → persist. 
faiss.ai

Title→QID map: from Wikidata sitelinks/dumps; export to SQLite. 
wikidata.org
+1

KG neighbor store: from dumps or cached WDQS queries; persist typed edges (QID1, rel, QID2, weight). 
wikidata.org
+1
7) Flutter ↔ backend contract (simple)

POST /answer body: { "q": "How to tune a 2.4 GHz patch antenna?" }

Response: { "answer": "...", "trace": { "n0":600, "n1":80, "n2":12, "evidence":[{id,title,url}, ...] } }

Your app renders the text and (optionally) evidence.

8) Sane default budgets (server-side)

𝑁
0
N
0
	​

=600 → Stage-1 
𝑁
1
N
1
	​

=80 → encode to layer 
𝐿
1
L
1
	​

=5 → Stage-2 
𝑁
2
N
2
	​

=12 → finish encode + decode; per-passage max 160 tokens; (optional) token-prune K=96 before decoder to cut cross-attention cost (per FiDO and follow-ups on token-level pruning).
