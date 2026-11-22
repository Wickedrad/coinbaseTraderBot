"""Round 15 loop 1b: a copy of the data folder whose BTC.D is BTC's share of the market without USDT and USDC.
BTC.D_x = BTC.D / (1 - (USDT.D + USDC.D)/100), daily o/h/l/c, stablecoin shares forward-filled and 0 before each series starts.
Usage: python3 -I make_exstables.py <data_dir> <out_dir>   (copy the other CSVs into out_dir yourself)"""
import sys
import pandas as pd

src, out = sys.argv[1], sys.argv[2]
b = pd.read_csv(f"{src}/BTC.D_1d.csv")
b["d"] = pd.to_datetime(b.ts, unit="ms").dt.normalize()


def ld(n):
    s = pd.read_csv(f"{src}/{n}_1d.csv")
    s["d"] = pd.to_datetime(s.ts, unit="ms").dt.normalize()
    return s.drop_duplicates("d", keep="last").set_index("d")["c"]


S = (ld("USDT.D").reindex(b.d).ffill().fillna(0).values + ld("USDC.D").reindex(b.d).ffill().fillna(0).values) / 100
for k in ["o", "h", "l", "c"]:
    b[k] = b[k] / (1 - S)
b.drop(columns=["d"]).to_csv(f"{out}/BTC.D_1d.csv", index=False)
print("last", b.c.iloc[-1], "max stable share", S.max())
