"""
Training réel: Elo baseline → Dixon-Coles → CatBoost + calibration isotonic.
Time split rolling strict as-of (spec §2 : prévention de fuite de données).

Règles implémentées ici :
  - load_features() : WHERE computed_at <= as_of  → aucune donnée future
  - rolling_splits() : folds temporels + embargo days → pas de fuite entre
    le train et la validation via des features calculées tardivement.
"""
import os
from datetime import datetime, timedelta

import pandas as pd


def load_features(as_of: str) -> pd.DataFrame:
    """Features STRICTEMENT antérieures ou égales à `as_of`.

    Fail-closed : sans DATABASE_URL ou sans table features, on ne fabrique
    aucun dataset (le code de training précédent retournait un DataFrame vide
    en silence, ce qui faisait croire à un entraînement réussi).
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("[TRAIN REAL] DATABASE_URL absent → aucun dataset (fail-closed)")
        return pd.DataFrame()

    try:
        import psycopg2
    except ImportError:
        print("[TRAIN REAL] psycopg2 absent → aucun dataset (fail-closed)")
        return pd.DataFrame()

    conn = psycopg2.connect(dsn)
    try:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM features
            WHERE computed_at <= %s
            ORDER BY computed_at ASC
            """,
            conn,
            params=(as_of,),
        )
    except Exception as e:
        print(f"[TRAIN REAL] lecture features impossible ({e}) → fail-closed")
        return pd.DataFrame()
    finally:
        conn.close()

    print(f"[TRAIN REAL] {len(df)} features <= {as_of} (time split strict)")
    return df


def rolling_splits(df: pd.DataFrame, n_splits: int = 5, embargo_days: int = 2):
    """Splits temporels rolling avec embargo.

    Pour chaque fold k :
      - train  : features dont computed_at <= t_k - embargo
      - valid  : features dans [t_k, t_k + horizon)
    L'embargo supprime la fenêtre juste avant le fold de validation, pendant
    laquelle des features peuvent avoir été recalculées avec de l'information
    postérieure au timestamp d'origine (le classique leak du time split).
    """
    if df.empty or 'computed_at' not in df.columns:
        return []

    ts = pd.to_datetime(df['computed_at']).sort_values().reset_index(drop=True)
    df = df.assign(computed_at=ts)
    horizon = max(1, len(df) // (n_splits + 1))

    splits = []
    for k in range(n_splits):
        start = horizon * (k + 1)
        end = min(start + horizon, len(df))
        if end <= start:
            continue
        t_k = df['computed_at'].iloc[start]
        train_end = t_k - timedelta(days=embargo_days)
        train = df[df['computed_at'] <= train_end]
        valid = df[(df['computed_at'] >= t_k) & (df['computed_at'] < df['computed_at'].iloc[end])]
        if len(train) == 0 or len(valid) == 0:
            continue
        splits.append({
            'fold': k + 1,
            'train_until': train_end.isoformat(),
            'valid_from': t_k.isoformat(),
            'train': train,
            'valid': valid,
        })
        print(f"[TRAIN REAL] fold {k+1}: train<={train_end.date()} (n={len(train)}) "
              f"valid (n={len(valid)})")
    return splits


def train():
    as_of = os.getenv("TRAIN_AS_OF") or datetime.utcnow().isoformat()
    df = load_features(as_of)
    if df.empty:
        print("[TRAIN REAL] aucun dataset → entraînement annulé (fail-closed)")
        return

    splits = rolling_splits(df)
    if not splits:
        print("[TRAIN REAL] pas assez de données pour un split rolling → fail-closed")
        return

    # 1. Elo (app/models/elo.py)
    # 2. Dixon-Coles (app/models/dixon_coles.py)
    # 3. CatBoost / LightGBM (optionnels, import guarded)
    # 4. Calibration isotonic (app/models/calibration.py)
    # 5. Validation rolling par ligue — ci-dessus
    # 6. Sauvegarde modèle versionné (Postgres model_versions + object storage)
    print(f"[TRAIN REAL] {len(splits)} folds temporels prêts — "
          f"brancher Elo/Dixon-Coles/CatBoost + calibration isotonic")


if __name__ == "__main__":
    train()
