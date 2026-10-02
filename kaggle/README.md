# kaggle/ - Kaggle packaging

Confirmed 2026-09-21: this platform's raw data IS the Kaggle dataset "IBM Transactions for Anti Money
Laundering (AML)" (https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml,
IBM Research / Altman et al., NeurIPS 2023). Unlike Customer360 Navigator (CFPB + BANKING77, neither
Kaggle-hosted), a Kaggle-notebook publication step is directly applicable here, the same way it was on AMEX
RiskIQ and Home Credit RiskIQ.

## Open items (not yet decided)
- Which size/ratio variant (HI- or LI-, Small/Medium/Large) gets placed in `data/raw/` - see
  `../docs/data_dictionary/RAW_DATA_MANIFEST.md` Section 2.
- Which BP(s) get a published Kaggle notebook (candidates: BP1 Suspicious Transaction Detection, BP4
  Transaction Network Analytics - graph/network notebooks tend to demo well) vs. which stay private.
- huggingface_space/ is kept as a scaffold for a possible BP6 GenAI SAR Narrative Assistant demo (Gradio/
  Streamlit), mirroring the option Customer360 Navigator left open for its own BP6.

Nothing is published from this folder until you confirm scope.

## huggingface_space/
Empty scaffold for a future Gradio/Streamlit demo app.py + requirements.txt.
