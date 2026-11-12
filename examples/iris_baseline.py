"""Real 1-nearest-neighbour evaluation of the public UCI Iris benchmark.

Data is downloaded separately. A seeded stratified holdout keeps 15 examples per
class for testing; scaling uses the training partition only. No hyperparameter
search is performed. This small demonstration cannot establish a novel result.
"""
import argparse
from collections import Counter, defaultdict
import csv
import io
import json
import math
from pathlib import Path
import random
import zipfile


def evaluate(data_path, output, seed):
    with zipfile.ZipFile(data_path) as archive:
        content = archive.read("bezdekIris.data").decode("utf-8")
    rows = []
    for row in csv.reader(io.StringIO(content)):
        if not row:
            continue
        if len(row) != 5:
            raise ValueError("Unexpected Iris row shape")
        features = [float(x) for x in row[:4]]
        if not all(math.isfinite(x) for x in features):
            raise ValueError("Non-finite observation")
        rows.append((features, row[4]))
    groups = defaultdict(list)
    for i, (_, label) in enumerate(rows):
        groups[label].append(i)
    if len(rows) != 150 or sorted(map(len, groups.values())) != [50, 50, 50]:
        raise ValueError("Dataset does not match the documented Iris benchmark")
    train, test = [], []
    rng = random.Random(seed)
    for label in sorted(groups):
        indices = groups[label][:]
        rng.shuffle(indices)
        test.extend(indices[:15])
        train.extend(indices[15:])
    if set(train) & set(test) or len(set(train + test)) != len(rows):
        raise ValueError("Invalid split")
    mean = [sum(rows[i][0][j] for i in train) / len(train) for j in range(4)]
    scale = [math.sqrt(sum((rows[i][0][j] - mean[j]) ** 2 for i in train) / len(train)) or 1.0 for j in range(4)]
    def standardized(i):
        return [(rows[i][0][j] - mean[j]) / scale[j] for j in range(4)]
    vectors = {i: standardized(i) for i in train + test}
    majority = sorted(Counter(rows[i][1] for i in train).items(), key=lambda x: (-x[1], x[0]))[0][0]
    predictions = []
    for i in test:
        nearest = min(train, key=lambda k: (sum((a - b) ** 2 for a, b in zip(vectors[i], vectors[k])), k))
        predictions.append({"row": i, "truth": rows[i][1], "prediction": rows[nearest][1], "majority": majority})
    metrics = {"accuracy": sum(x["truth"] == x["prediction"] for x in predictions) / len(test),
               "majority_accuracy": sum(x["truth"] == majority for x in predictions) / len(test),
               "n_train": len(train), "n_test": len(test)}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("metrics.json", metrics), ("split.json", {"seed": seed, "train": train, "test": test, "training_mean": mean, "training_scale": scale})):
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "predictions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["row", "truth", "prediction", "majority"])
        writer.writeheader()
        writer.writerows(predictions)
    print(json.dumps(metrics))
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    evaluate(args.data, args.output, args.seed)
