# Search evaluation set

Use this folder to measure search quality, so that changes to thresholds, `k`, the text model or the search mode are judged with numbers instead of guesses.

## 1. Build the cases (50–100 is a good start)

Create a skeleton from movies that are actually in your index:

```bash
cd django_project
python manage.py build_eval_cases ../eval/cases.jsonl --count 80
```

Then fill in each line:

- **`text`:** describe the movie in your own words, the way a user of the bot would. Don't copy the IMDb plot: the index already contains it, so a copy would be graded far too generously. Mix short and long descriptions.
- **`image`:** put a screenshot or a phone photo of the screen in `eval/images/` and write its path, relative to the JSONL file, for example `images/case-001.jpg`. Include photos where the main actors are visible, and a few without faces (for scene search).
- **Both:** some cases can have a photo and a caption, like a user sending a photo with a description.

Also add some **negative cases** (about 10–20%): describe movies that are *not* in your collection and set `"expected_imdb_id": null`. The right answer for those is "not enough information", so they teach the threshold sweep which scores to reject. Without them, the suggested threshold can only learn what to accept.

Lines with neither `text` nor `image` are skipped. The format is described in `cases.example.jsonl`.

## 2. Run it

```bash
python manage.py evaluate_search --cases ../eval/cases.jsonl
python manage.py evaluate_search --cases ../eval/cases.jsonl --mode hybrid
python manage.py evaluate_search --cases ../eval/cases.jsonl --mode passages   # needs rebuild_indices passages
python manage.py evaluate_search --cases ../eval/cases.jsonl --no-preprocess
python manage.py evaluate_search --faces 300        # no labelling needed, see below
```

The command prints, per kind of query (`text`, `image`, `image+text`):

- **`hit@1`:** how often the correct movie is the first answer.
- **`hit@3`:** how often it is in the top 3.
- **`mrr`:** mean reciprocal rank: 1 when always first, 0.5 when always second, and so on.

It also prints a **suggested `THRESHOLD_TEXT`** (and `THRESHOLD_SCENE`): the cutoff that best separates correct top answers from wrong ones (it maximises F1). Set it in the Django admin, under Constance → Search options.

`--faces N` needs no labels. It takes N indexed face images, searches with each image's own vector while excluding that image, and checks that the vote returns the same actor (leave-one-out). It reports the accuracy and a **suggested `THRESHOLD_IMAGE`**.

Add `--output report.json` to save all numbers and compare runs.

## Tips

- Keep `cases.jsonl` stable once it's written. Comparing runs on the same cases is what makes the numbers meaningful.
- Don't tune the thresholds on the same few cases you look at by hand. With fewer than about 50 cases, treat the suggested values as rough.
