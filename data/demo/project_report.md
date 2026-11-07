# SYNTHETIC DEMO — Classifying Medical Images

> **SYNTHETIC DEMO DATA.** This report is fictional and was written only to demo BusFactor.
> It does not describe real patients, a real dataset or real results.
> Pages are separated by `---` lines; page numbers count from 1.

**Course:** Machine Learning (group project) · **Project ID:** P01
**Team:** Member A (M01), Member B (M02), Member C (M03), Member D (M04)

## 1. Introduction

Our goal was to classify chest X-ray images as "finding" or "no finding". The dataset has 4,200 images collected at a single hospital. About 12% of the images show a finding, so the classes are strongly imbalanced.

## 2. Data preparation (Member A)

When we first looked at the data we found 310 exact or near-exact duplicate images and 95 images with a missing label. We removed duplicate images and imputed missing labels before training, because duplicates could leak between the training and test sets and inflate our scores. Missing labels were imputed from the radiologist's free-text note when the note was clear; the remaining 14 images without a clear note were dropped.

---

## 3. Model selection (Member B)

We compared two simple baselines on features extracted from a pretrained network. We chose Random Forest instead of Logistic Regression as our baseline because it captured non-linear interactions between features without manual feature engineering. Logistic Regression was faster and easier to interpret, but it scored clearly lower on the validation set.

## 4. Evaluation metric (Member B)

We report F1 instead of accuracy as our headline metric because of the class imbalance. A model that always predicts "no finding" would already reach about 88% accuracy while detecting no finding at all. F1 combines precision and recall on the minority class, so it only goes up when the model actually finds positive cases.

---

## 5. Data split (Member C)

We used a stratified train/validation/test split (70/15/15) so that each subset keeps the same share of positive images as the full dataset. With a random split, the small test set could by chance contain very few positive images, which would make the F1 score unstable.

## 6. Results

The Random Forest baseline reached F1 = 0.71 on the test set (synthetic number for the demo).

---

## 7. Limitations (Member D)

The model was not tested on images from other hospitals, so we cannot claim it generalises to different scanners or patient populations. All 4,200 images come from one hospital and one type of scanner. A next step would be an external validation set from at least one other hospital.
