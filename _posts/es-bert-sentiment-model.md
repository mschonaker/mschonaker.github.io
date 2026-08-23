---
id: es-bert-sentiment
title: Train a Tiny Sentiment Model and Deploy It Inside Elasticsearch
summary: Train a 1M-parameter BERT from random weights on your own labeled CSV, load it into Elasticsearch 9.x with Eland, and enrich documents at indexing time.
date: 2026-08-22
image: /images/es-bert-sentiment-header.png
---

# Train a Tiny Sentiment Model and Deploy It Inside Elasticsearch

Elasticsearch can run transformer models and attach their output to documents as you index them. This post walks the full loop with the smallest possible example. We build a BERT with about one million parameters from random weights, train it on a CSV of your own labeled examples, load it into Elasticsearch 9.x with Eland, and let an ingest pipeline stamp sentiment on every new document.

No pretrained weights, no quality targets. The goal is a working end-to-end pipeline you can run on a laptop, then improve later by editing one config block.

## What You Need

- [uv](https://docs.astral.sh/uv/) for the Python environment
- Docker
- A few gigabytes of free disk space for the Docker image and model files

Versions used in this post:

| Component | Version |
|-----------|---------|
| Python | 3.12.9 |
| torch | 2.7.1 |
| transformers | 4.57.6 |
| eland | 9.2.0 |
| datasets | 5.0.1 |
| Elasticsearch | 9.5.2 |

## Run Elasticsearch

```bash
docker run -d --name es9 \
  -p 9200:9200 \
  -e discovery.type=single-node \
  -e xpack.security.enabled=false \
  docker.elastic.co/elasticsearch/elasticsearch:9.5.2
```

Deploying your own models is a Platinum-tier feature. The free trial unlocks it:

```bash
curl -X POST 'http://localhost:9200/_license/start_trial?acknowledge=true'
```

## Set Up Python

```bash
uv init --bare
uv add 'eland[pytorch]' 'transformers[torch]' datasets
```

The `transformers[torch]` extra matters. The `Trainer` class needs `accelerate`, and plain `transformers` does not pull it in. Without it, training fails at `TrainingArguments` with an import error.

## Train With Your Own Data

Training starts from a plain CSV: one `text` column, one integer `label` column. Here zero means negative, one means positive. Create a small file to see the full shape end to end:

```bash
cat > reviews.csv <<'EOF'
text,label
"absolutely love it, works like a charm",1
"broke after two days, total waste of money",0
"great sound quality for the price",1
"customer support never answered me",0
"setup took five minutes and everything paired instantly",1
"the battery dies within an hour",0
"solid build and feels premium",1
"cheap plastic, stopped working in a week",0
EOF
```

This sample only proves the plumbing. For a real model, bring your own domain: label a few hundred examples per class from your reviews, tickets, or survey answers, and replace the file. Extra classes work too — add them to the CSV and update `num_labels` and `id2label` in the script.

We reuse the standard uncased wordpiece vocabulary to skip tokenizer training, and build the smallest transformer that still works: one layer, hidden size 32, two attention heads. That lands near one million parameters and trains in minutes on CPU or Apple Silicon.

```python
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    BertConfig,
    BertForSequenceClassification,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

MODEL_DIR = "model-out"
MAX_LENGTH = 128


def main():
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased", use_fast=False)

    data = load_dataset("csv", data_files="reviews.csv", split="train")
    splits = data.train_test_split(test_size=0.2, seed=42)

    def encode(batch):
        return tokenizer(batch["text"], truncation=True, max_length=MAX_LENGTH)

    encoded = splits.map(encode, batched=True, remove_columns=["text"])

    config = BertConfig(
        vocab_size=tokenizer.vocab_size,
        hidden_size=32,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=64,
        max_position_embeddings=MAX_LENGTH,
        num_labels=2,
        id2label={0: "NEGATIVE", 1: "POSITIVE"},
        label2id={"NEGATIVE": 0, "POSITIVE": 1},
    )
    model = BertForSequenceClassification(config)

    args = TrainingArguments(
        output_dir="checkpoints",
        num_train_epochs=2,
        per_device_train_batch_size=64,
        learning_rate=1e-3,
        logging_steps=200,
        eval_strategy="epoch",
        save_strategy="no",
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=encoded["train"],
        eval_dataset=encoded["test"],
        data_collator=DataCollatorWithPadding(tokenizer),
    )
    trainer.train()
    print(trainer.evaluate())

    trainer.save_model(MODEL_DIR)
    tokenizer.model_max_length = MAX_LENGTH
    tokenizer.save_pretrained(MODEL_DIR)


if __name__ == "__main__":
    main()
```

Run it:

```bash
uv run train.py
```

The script holds out 20 percent of the rows for evaluation, so the metrics printed after training say something honest about the model. With the eight-row sample they will be noisy; that is expected. Scale up the CSV and the same script does the real work.

Three details make the model export cleanly later:

- `id2label` flows through Eland into Elasticsearch. Inference results come back with `POSITIVE` and `NEGATIVE` names instead of `LABEL_0` and `LABEL_1`.
- Eland reads the tokenizer's `model_max_length` as the cluster-side tokenization limit. Saving it as 128 matches the tiny model's position limit, so long inputs stay valid.
- The tokenizer loads with `use_fast=False`. The TorchScript tracing path in Eland uses the slow tokenizer implementation.

## Import and Deploy With Eland

Elasticsearch runs models as TorchScript, not raw checkpoints. [Eland](https://www.elastic.co/docs/reference/elasticsearch/clients/eland/machine-learning) converts the model, chunks it, uploads it, and starts it. The `eland_import_hub_model` shell script wraps these calls, but the same steps exist as a library, so we do it from Python:

```python
import os

from eland.ml.pytorch import PyTorchModel
from eland.ml.pytorch.transformers import TransformerModel
from elasticsearch import Elasticsearch, NotFoundError

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
MODEL_DIR = "model-out"
EXPORT_DIR = "models"
ES_MODEL_ID = "sentiment-tiny"


def replace_existing_model(es):
    es.ml.stop_trained_model_deployment(model_id=ES_MODEL_ID, allow_no_match=True)
    try:
        es.ml.delete_trained_model(model_id=ES_MODEL_ID)
    except NotFoundError:
        pass


def main():
    es = Elasticsearch(ES_URL)
    print(f"connected to elasticsearch {es.info()['version']['number']}")

    os.makedirs(EXPORT_DIR, exist_ok=True)
    tm = TransformerModel(model_id=MODEL_DIR, task_type="text_classification")
    model_path, config, vocab_path = tm.save(EXPORT_DIR)

    replace_existing_model(es)

    ptm = PyTorchModel(es, ES_MODEL_ID)
    ptm.import_model(
        model_path=model_path,
        config_path=None,
        vocab_path=vocab_path,
        config=config,
    )

    es.ml.start_trained_model_deployment(model_id=ES_MODEL_ID, timeout="5m")
    print(f"deployed {ES_MODEL_ID}")


if __name__ == "__main__":
    main()
```

```bash
uv run import_model.py
```

Notes for your own version of this script:

- All `elasticsearch-py` client methods take keyword arguments only.
- The stop and delete calls clear any previous copy, so you can rerun after each training round.
- Create the export directory yourself; `torch.jit.save` does not make it.

## Test Inference

```bash
curl -X POST 'http://localhost:9200/_ml/trained_models/sentiment-tiny/_infer' \
  -H 'Content-Type: application/json' -d'
{
  "docs": [{ "text_field": "I loved this movie" }]
}'
```

```json
{
  "inference_results": [
    { "predicted_value": "POSITIVE", "prediction_probability": 0.9936 }
  ]
}
```

In 8.x this endpoint was `/deployment/_infer`. Version 9.x removed that path. One `_infer` route now serves both deployed and undeployed models.

## Enrich Documents at Indexing Time

Create an ingest pipeline that runs the model on every document passing through it:

```bash
curl -X PUT 'http://localhost:9200/_ingest/pipeline/sentiment' \
  -H 'Content-Type: application/json' -d'
{
  "processors": [
    {
      "inference": {
        "model_id": "sentiment-tiny",
        "field_map": { "review": "text_field" }
      }
    }
  ]
}'
```

Create an index with fields for the results:

```bash
curl -X PUT 'http://localhost:9200/reviews' \
  -H 'Content-Type: application/json' -d'
{
  "mappings": {
    "properties": {
      "review": { "type": "text" },
      "ml.inference.predicted_value": { "type": "keyword" },
      "ml.inference.prediction_probability": { "type": "rank_feature" }
    }
  }
}'
```

The probability maps to `rank_feature` rather than `float`: it stores almost nothing on its own, but feeds straight into relevance ranking. Values must be positive, which class probabilities always satisfy.

Index a document with `?pipeline=sentiment`:

```bash
curl -X PUT 'http://localhost:9200/reviews/_doc/1?pipeline=sentiment' \
  -H 'Content-Type: application/json' -d'
{
  "review": "what a delightful film, the cast was superb"
}'
```

The stored document gains the inference block:

```json
{
  "review": "what a delightful film, the cast was superb",
  "ml": {
    "inference": {
      "predicted_value": "POSITIVE",
      "prediction_probability": 0.9938,
      "model_id": "sentiment-tiny"
    }
  }
}
```

Bulk loads take the same parameter on `_bulk`. To backfill existing data, reindex with `"dest": { "pipeline": "sentiment" }`.

## Search

From here everything is ordinary Elasticsearch. Filter on the predicted class:

```bash
curl 'http://localhost:9200/reviews/_search' \
  -H 'Content-Type: application/json' -d'
{
  "query": {
    "term": { "ml.inference.predicted_value": "POSITIVE" }
  }
}'
```

Or summarize the split with an aggregation:

```bash
curl 'http://localhost:9200/reviews/_search' \
  -H 'Content-Type: application/json' -d'
{
  "size": 0,
  "aggs": {
    "sentiments": {
      "terms": { "field": "ml.inference.predicted_value" }
    }
  }
}'
```

The `rank_feature` mapping pays off when text relevance and model confidence should share one score. Here, matches on the review text get boosted by how sure the model is:

```bash
curl 'http://localhost:9200/reviews/_search' \
  -H 'Content-Type: application/json' -d'
{
  "query": {
    "bool": {
      "must": {
        "match": { "review": "battery" }
      },
      "should": {
        "rank_feature": {
          "field": "ml.inference.prediction_probability",
          "saturation": { "pivot": 0.9 }
        }
      }
    }
  }
}'
```

How does the boost work? The query adds `S / (S + pivot)` to every hit's score, where `S` is the stored probability. The `pivot` is the value that earns half credit: with `pivot: 0.9`, a confident 0.99 contributes about 0.52 points while a hesitant 0.78 contributes about 0.46. Small amounts, but they decide close matches. Leave out `saturation` and Elasticsearch picks the pivot for you as the geometric mean of the field's values.

One restriction to know: `rank_feature` fields cannot be filtered, sorted, or aggregated — they only participate in scoring. That is why this mapping keeps the two model outputs apart: the class label stays a `keyword` for filtering and aggregation, the probability becomes a `rank_feature` for ranking.

Search never touches the model. By query time, sentiment is just stored fields, so queries stay fast.

## Iterating on Quality

This model is weak by design. When you want better results, change the config numbers in `train.py`: grow `hidden_size`, add layers, or train more epochs. For a bigger jump, start from pretrained weights such as `distilbert-base-uncased`. Then rerun the two scripts. The import script replaces the deployed model, and every step after training stays identical.

One lever matters more than model size: the training data itself. Swap in labeled examples from your own domain and rerun the two scripts. The import script replaces the deployed model, and every step after training stays identical.

## References

### Official Sources

- [NLP tutorial: load a trained model and enrich data](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/nlp-example.html) — Elastic documentation
- [Import the trained model and vocabulary](https://www.elastic.co/docs/explore-analyze/machine-learning/nlp/ml-nlp-import-model) — Elastic documentation
- [Deploy trained models](https://www.elastic.co/docs/explore-analyze/machine-learning/nlp/ml-nlp-deploy-models) — Elastic documentation
- [Eland machine learning client](https://www.elastic.co/docs/reference/elasticsearch/clients/eland/machine-learning) — Elastic documentation
- [Elastic subscriptions](https://www.elastic.co/subscriptions) — License tiers for model deployment

### Ecosystem Sources

- [Loading data with Hugging Face datasets](https://huggingface.co/docs/datasets/loading) — CSV and other local formats
- [Eland GitHub repository](https://github.com/elastic/eland) — source for the PyTorch tracing path
- [uv documentation](https://docs.astral.sh/uv/) — project and environment management
