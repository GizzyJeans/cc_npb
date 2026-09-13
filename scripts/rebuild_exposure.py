"""最小重建版: 各隊球場曝險。球場名在賽程頁可能含全形空白 (神 宮 / 横 浜)，
所以先把空白全部去掉再比對。"""
import re, json, glob
import sys; sys.path.insert(0,'/home/user/cc_npb')
from config import calibration_2026 as cal

TEAMS={'ヤクルト','広島','中日','阪神','巨人','DeNA','日本ハム','西武',
       'ソフトバンク','ロッテ','楽天','オリックス'}
PARK={'神宮':'神宮','横浜':'横浜','甲子園':'甲子園','東京ドーム':'東京ドーム',
      'バンテリンドーム':'バンテリンドーム','マツダ':'マツダスタジアム',
      'ベルーナドーム':'ベルーナドーム','京セラD大阪':'京セラD大阪',
      'みずほPayPay':'みずほPayPay','ZOZOマリン':'ZOZOマリン',
      '楽天モバイル':'楽天モバイル','エスコン':'エスコンＦ'}

expo={t:[] for t in TEAMS}
pat=re.compile(r'(\S+?)(\d+)-(\d+)(\S+?)(\S+?)(\d+):(\d+)')
for f in sorted(glob.glob('sched_*.html')):
    s=open(f,encoding='utf-8',errors='replace').read()
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', s, flags=re.S):
        cells=[re.sub(r'\s+','',re.sub(r'<[^>]+>','',c))
               for c in re.findall(r'<td[^>]*>(.*?)</td>', tr, flags=re.S)]
        if len(cells) < 3: continue
        blob="".join(cells)
        hs=[t for t in TEAMS if t in blob]
        if len(hs) < 2: continue
        pk=next((PARK[k] for k in PARK if k in blob), None)
        if not pk: continue
        if not re.search(r'\d+-\d+', blob): continue      # 只算已打完的
        pf=cal.PARK_FACTORS_2026.get(pk)
        if not pf: continue
        for t in hs: expo[t].append(pf)
print("各隊球場曝險:")
EXPO={}
for t,v in sorted(expo.items()):
    EXPO[t]=sum(v)/len(v) if v else 1.0
    print("  %-9s %3d 場  %.4f" % (t,len(v),EXPO[t]))
json.dump(EXPO, open('expo.json','w'), ensure_ascii=False, indent=1)
