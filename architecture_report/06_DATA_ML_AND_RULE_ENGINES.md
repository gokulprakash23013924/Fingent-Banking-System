# Fingent Data Architecture, ML Models & Rule Engines

This document details the data structures, machine learning models, and deterministic rule engines that power **Fingent**. All business-critical decisions (interest rates, eligibility thresholds, and fraud flags) are implemented deterministically, guaranteeing reproducibility and audit compliance.

---

## 1. Demo Personas & Seed Profiles

The system seeds ten customer profiles (`data/seed.py`) representing common banking scenarios:

| ID | Name | City | Segment | Income / mo | CIBIL | KYC Status | Primary Persona Description |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **C001** | Aarav Mehta | Mumbai | Prime | ₹1,20,000 | 780 | Verified | **Prime Customer**: High bureau score, eligible for full personal loans (₹5L+). |
| **C002** | Diya Nair | Kochi | Retail | ₹45,000 | 710 | Verified | **Fraud Victim**: Suspicious ₹48,000 POS transaction at 03:00 AM outside home region. |
| **C003** | Rohan Das | Kolkata | Mass | ₹35,000 | 580 | Verified | **Subprime Borrower**: Low bureau score (<650), triggers automatic policy decline. |
| **C004** | Meera Iyer | Chennai | Emerging | ₹90,000 | 740 | Pending | **Pending KYC**: High earner with strong credit, but loan activation held due to pending KYC. |
| **C005** | Karthik Raman | Bengaluru | Retail | ₹60,000 | 690 | Verified | **High DTI / Overleveraged**: High existing EMI obligations (FOIR limit reached). |
| **C006** | Sana Khan | Hyderabad | Retail | ₹52,000 | 705 | Verified | **Risky Transaction Signals**: Multiple recent fraud alerts requiring manual review. |
| **C007** | Vikram Singh | Delhi | Business | ₹1,50,000 | 810 | Verified | **High Net Worth**: Multi-account profile (Savings + Current). |
| **C008** | Ananya Rao | Pune | Retail | ₹40,000 | 660 | Verified | **Marginal Approval**: Eligible for lower loan tiers at 14.0% p.a. |
| **C009** | Imran Sheikh | Lucknow | Mass | ₹28,000 | 640 | Expired | **Expired KYC**: KYC last verified >365 days ago, write operations blocked. |
| **C010** | Lakshmi Pillai | Coimbatore| Retail | ₹70,000 | 730 | Flagged | **AML Watchlist**: Sanctions screening flag, triggers mandatory compliance hold. |

---

## 2. Machine Learning: Fraud Anomaly Engine (Isolation Forest)

Implemented in `app/ml/fraud.py`, fraud detection combines deterministic rule scoring with an unsupervised **Isolation Forest** anomaly model.

### 2.1 Feature Vectorization
Every transaction is converted into a 6-dimensional feature vector:

$$\mathbf{x} = \begin{bmatrix} 
\text{clip}(z_{\text{amount}}, -5.0, 10.0) \\
\text{hour} / 23.0 \\
\mathbb{I}_{\text{foreign}} \\
\mathbb{I}_{\text{new\_device}} \\
\mathbb{I}_{\text{new\_merchant}} \\
\min(v_{\text{velocity}}, 5) 
\end{bmatrix}$$

1. **Log-Space Amount Z-Score ($z_{\text{amount}}$)**: Financial spend is right-skewed. To prevent a single large purchase from skewing the baseline, spend is evaluated in log space:
   $$z_{\text{amount}} = \frac{\ln(\max(\text{amount}, 1)) - \mu_{\ln}}{\max(\sigma_{\ln}, 0.25)}$$
2. **Normalized Hour**: Time of transaction divided by 23.0.
3. **Foreign Country Flag**: $1$ if originating outside customer's home country (`c.home_country`), else $0$.
4. **New Device Flag**: $1$ if transaction `device_id` is not registered in the customer's known devices table.
5. **New Merchant Flag**: $1$ if this is the customer's first payment to the merchant.
6. **Velocity**: Count of transactions occurring within a 10-minute window.

### 2.2 Anomaly Score Normalization
The Isolation Forest produces sample scores $s = -\text{score\_samples}(\mathbf{x})$:
$$\text{anomaly} = \text{clip}\left(\frac{s - 0.5}{0.3}, 0.0, 1.0\right)$$
The anomaly bonus is added to the deterministic rule score:
$$\text{Final Score} = \min\left(100, \text{Score}_{\text{rules}} + \text{round}(w_{\text{anomaly}} \times \text{anomaly})\right)$$

### 2.3 Decision Thresholds
- **Score $\ge 80$**: $\rightarrow \text{"block"}$ (Card frozen, immediate dispute staged)
- **Score $50\text{–}79$**: $\rightarrow \text{"review"}$ (Flagged for supervisor review)
- **Score $< 50$**: $\rightarrow \text{"allow"}$ (Normal transaction approved)

---

## 3. Deterministic Business Rule Engines

All financial business logic is contained in `app/rules.py`, strictly decoupled from LLM models and I/O.

### 3.1 Personal Loan EMI Formula
Fingent computes monthly installments using the standard banking amortization equation:
$$\text{EMI} = P \cdot r \cdot \frac{(1 + r)^n}{(1 + r)^n - 1}$$
where:
- $P$: Principal loan amount in INR.
- $r$: Monthly interest rate ($\text{annual\_rate} / 12 / 100$).
- $n$: Tenure in months.

### 3.2 Maximum Borrowing Capacity (Principal from EMI)
To determine the maximum eligible loan amount given a customer's remaining disposable income:
$$P_{\max} = \text{EMI}_{\max} \cdot \frac{(1 + r)^n - 1}{r \cdot (1 + r)^n}$$

### 3.3 Lending Policy Rate Card
Interest rates are tied deterministically to credit bureau scores:

| CIBIL Score Tier | Annual Interest Rate | Lending Risk Category |
| :--- | :--- | :--- |
| **Score $\ge 750$** | **10.5% p.a.** | Prime / Super-Prime |
| **Score $700\text{–}749$** | **12.0% p.a.** | Standard Retail |
| **Score $650\text{–}699$** | **14.0% p.a.** | Sub-Prime (Higher Risk) |
| **Score $< 650$** | **Ineligible** | Declined (Below Policy Minimum) |

### 3.4 Multi-Factor Underwriting Rules (FOIR & Income Cap)
Loan approval requires all the following rules to pass:
1. **Minimum / Maximum Amount**: $₹50,000 \le \text{amount} \le ₹15,00,000$.
2. **Tenure Window**: $12 \le \text{tenure} \le 60\text{ months}$.
3. **Credit Bureau Minimum**: $\text{CIBIL} \ge 650$.
4. **Income Multiplier Cap**: $\text{amount} \le 10 \times \text{monthly\_income}$.
5. **Fixed Obligation to Income Ratio (FOIR)**:
   $$\text{FOIR} = \frac{\text{existing\_emi} + \text{new\_emi}}{\text{monthly\_income}} \le 50\%$$

---

## 4. Statistical Machine Learning: Intent Classifier

Implemented in `app/ml/intent_model.py`:
- **Architecture**: Scikit-Learn pipeline consisting of `TfidfVectorizer(ngram_range=(1, 2), min_df=1)` and `LogisticRegression(C=5.0, max_iter=200)`.
- **Dataset**: Curated banking utterances covering balance inquiries, transaction statements, fraud reporting, card controls, loan eligibility, EMI calculators, and alert lookups (`app/ml/training_data.py`).
- **Confidence Calibration**: Emits full probability distributions. If top confidence $< 0.70$, the query climbs to Tier 2 in the ladder rather than forcing an inaccurate classification.
