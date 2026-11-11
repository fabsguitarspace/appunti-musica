#!/usr/bin/env python3
"""Varianti del logo per la homepage dei tre volumi di appunti.

Dal logo originale (chitarra rossa in orbita) ricava:

- logo-teoria.png      chitarra blu notte; 12 tacche sul cerchio grande, come il
                       circolo delle quinte, con il Do in evidenza in alto
- logo-pratica.png     chitarra rossa originale; il pianeta diventa un plettro
- logo-repertorio.png  chitarra color ottone; il pianeta diventa un disco in vinile

Il logo originale resta invariato e continua a essere usato nella barra in alto.

Uso:  python3 logo_variants.py LOGO_ORIGINALE.png CARTELLA_DI_USCITA
Richiede Pillow e numpy. Le coordinate si riferiscono al logo di 693×693 px e
vengono scalate se l'immagine ha un'altra dimensione.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BASE = 693                      # lato del logo su cui sono state misurate le coordinate
PLANET = (139.5, 538.0, 31.0)   # centro x, centro y, raggio del pianeta
RING = (339.9, 345.4, 264.0)    # centro x, centro y, raggio del cerchio grande
SS = 4                          # sovracampionamento per bordi morbidi

COLORS = {                      # tinta (gradi), moltiplicatori di saturazione e luminosità
    'teoria': (218, 0.85, 0.85),
    'pratica': None,            # colori originali
    'repertorio': (38, 0.90, 1.00),
}
INK = {'teoria': (38, 70, 140), 'repertorio': (176, 128, 52)}


def recolor(img, hue, sat_mul, val_mul):
    """Ricolora solo i pixel molto saturi (la chitarra); beige e grigi restano intatti."""
    alpha = img.getchannel('A')
    hsv = np.asarray(img.convert('RGB').convert('HSV')).astype(float)
    mask = hsv[..., 1] > 110
    hsv[..., 0] = np.where(mask, (hue / 360 * 255) % 256, hsv[..., 0])
    hsv[..., 1] = np.where(mask, np.clip(hsv[..., 1] * sat_mul, 0, 255), hsv[..., 1])
    hsv[..., 2] = np.where(mask, np.clip(hsv[..., 2] * val_mul, 0, 255), hsv[..., 2])
    out = Image.fromarray(hsv.astype('uint8'), 'HSV').convert('RGB').convert('RGBA')
    out.putalpha(alpha)
    return out


def layer(size):
    """Livello trasparente sovracampionato e funzione di scala delle coordinate."""
    k = size / BASE * SS
    return Image.new('RGBA', (size * SS, size * SS), (0, 0, 0, 0)), (lambda v: v * k)


def flatten(img, big):
    img.alpha_composite(big.resize(img.size, Image.LANCZOS))
    return img


def radial_disc(big, cx, cy, r, inner, outer, light=(-0.35, -0.35)):
    """Disco con sfumatura radiale da `inner` (zona illuminata) a `outer`."""
    n = int(r * 2) + 2
    yy, xx = np.mgrid[0:n, 0:n].astype(float) - r
    lx, ly = light[0] * r, light[1] * r
    t = np.clip(np.hypot(xx - lx, yy - ly) / (r * 1.6), 0, 1)[..., None]
    rgb = np.array(inner) * (1 - t) + np.array(outer) * t
    a = (np.hypot(xx, yy) <= r) * 255
    disc = Image.fromarray(np.dstack([rgb, a]).astype('uint8'), 'RGBA')
    big.alpha_composite(disc, (int(cx - r), int(cy - r)))


def erase_planet(img):
    """Rende trasparente il pianeta originale: lo sfondo del logo è trasparente."""
    k = img.width / BASE
    cx, cy, r = (v * k for v in PLANET)
    r += 1.5 * k
    alpha = np.asarray(img.getchannel('A')).copy()
    yy, xx = np.mgrid[0:img.height, 0:img.width]
    alpha[np.hypot(xx - cx, yy - cy) <= r] = 0
    img.putalpha(Image.fromarray(alpha))


def shadow(big, s, offset=(2.5, 3.0), blur=3.0, scale=1.0):
    cx, cy, r = (s(v) for v in PLANET)
    r *= scale
    sh = Image.new('RGBA', big.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx - r + s(offset[0]), cy - r + s(offset[1]),
                                cx + r + s(offset[0]), cy + r + s(offset[1])], fill=(60, 45, 30, 70))
    big.alpha_composite(sh.filter(ImageFilter.GaussianBlur(s(blur))))


def vinyl(img):
    """Repertorio: disco in vinile con solchi ed etichetta color ottone."""
    erase_planet(img)
    big, s = layer(img.width)
    shadow(big, s, scale=1.02)
    cx, cy, r = (s(v) for v in PLANET)
    r *= 1.06
    radial_disc(big, cx, cy, r, (78, 74, 72), (22, 20, 20))
    d = ImageDraw.Draw(big)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(226, 210, 190, 200), width=int(s(1.0)))  # bordo per il tema scuro
    for i, rr in enumerate(np.linspace(r * 0.42, r * 0.95, 9)):    # solchi
        tone = 70 if i % 3 else 95
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(tone, tone, tone, 150), width=max(1, int(s(0.35))))
    d.arc([cx - r * 0.86, cy - r * 0.86, cx + r * 0.86, cy + r * 0.86], 200, 250,    # riflesso
          fill=(235, 228, 215, 120), width=int(s(1.6)))
    d.arc([cx - r * 0.66, cy - r * 0.66, cx + r * 0.66, cy + r * 0.66], 205, 240,
          fill=(235, 228, 215, 90), width=int(s(1.1)))
    radial_disc(big, cx, cy, r * 0.32, (232, 190, 110), (170, 118, 45))   # etichetta
    hole = r * 0.05
    d.ellipse([cx - hole, cy - hole, cx + hole, cy + hole], fill=(250, 246, 238, 255))
    return flatten(img, big)


def hull(points):
    """Inviluppo convesso (monotone chain)."""
    pts = sorted(set(points))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def pick(img):
    """Pratica: plettro color avorio, inclinato come se ruotasse in orbita."""
    erase_planet(img)
    big, s = layer(img.width)
    shadow(big, s, scale=0.95)
    cx, cy, r = (s(v) for v in PLANET)
    r *= 1.12
    # Plettro classico: inviluppo convesso di due spalle larghe e una punta stretta,
    # punta verso il basso, ruotato di 25°.
    circles = [(-0.52, -0.40, 0.46), (0.52, -0.40, 0.46), (0.0, 0.78, 0.14)]
    pts = hull([(r * (x + c * math.cos(t)), r * (y + c * math.sin(t)))
                for x, y, c in circles for t in np.linspace(0, 2 * math.pi, 90)])
    ang = math.radians(-25)
    pts = [(cx + x * math.cos(ang) - y * math.sin(ang), cy + x * math.sin(ang) + y * math.cos(ang))
           for x, y in pts]
    mask = Image.new('L', big.size, 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    fill = Image.new('RGBA', big.size, (0, 0, 0, 0))
    radial_disc(fill, cx, cy, r * 1.05, (246, 238, 224), (150, 132, 112))
    big.paste(fill, (0, 0), Image.composite(fill.getchannel('A'), Image.new('L', big.size, 0), mask))
    d = ImageDraw.Draw(big)
    d.line(pts + [pts[0]], fill=(120, 100, 80, 200), width=int(s(0.8)))
    d.arc([cx - r * 0.62, cy - r * 0.75, cx + r * 0.32, cy + r * 0.15], 195, 250,
          fill=(255, 252, 245, 190), width=int(s(1.6)))
    return flatten(img, big)


def ring_run(arr, angle):
    """Tratto del cerchio grande lungo il raggio all'angolo dato: (inizio, fine) o None.

    Il cerchio è disegnato a mano e non è perfettamente circolare: si cerca, lungo il
    raggio, il tratto beige continuo più vicino al raggio medio.
    """
    cx, cy, R = RING
    k = arr.shape[1] / BASE
    hits = []
    for rr in range(int(R * 0.78), int(R * 1.3)):
        x, y = (cx + rr * math.cos(angle)) * k, (cy + rr * math.sin(angle)) * k
        if not (0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]):
            continue
        r_, g_, b_, a_ = arr[int(y), int(x)]
        if a_ > 200 and r_ >= g_ >= b_ and r_ > 200 and 20 <= r_ - b_ <= 75:
            hits.append(rr)
    runs = []
    for h in hits:
        if runs and h - runs[-1][-1] <= 2:
            runs[-1].append(h)
        else:
            runs.append([h])
    runs = [r for r in runs if len(r) >= 6]
    if not runs:
        return None
    best = min(runs, key=lambda r: abs((r[0] + r[-1]) / 2 - R * 1.04))
    return best[0], best[-1]


def fifths(img):
    """Teoria: dodici tacche sul cerchio grande, come un quadrante; il Do in alto è evidenziato."""
    big, s = layer(img.width)
    arr = np.asarray(img).astype(int)
    cx, cy, _ = RING
    d = ImageDraw.Draw(big)
    for i in range(12):
        t = math.radians(-90 + 30 * i)
        run = ring_run(arr, t)
        if run is None:           # cerchio nascosto dalla chitarra: nessuna tacca
            continue
        a, b = run[0] - 6, run[1] + 6
        p1 = (s(cx + a * math.cos(t)), s(cy + a * math.sin(t)))
        p2 = (s(cx + b * math.cos(t)), s(cy + b * math.sin(t)))
        if i == 0:
            m = (run[0] + run[1]) / 2
            X, Y, Rd = s(cx + m * math.cos(t)), s(cy + m * math.sin(t)), s(8)
            d.ellipse([X - Rd, Y - Rd, X + Rd, Y + Rd], fill=INK['teoria'] + (255,),
                      outline=(250, 244, 232, 255), width=int(s(1.6)))
        else:
            d.line([p1, p2], fill=(132, 106, 82, 255), width=int(s(3.2)))
    return flatten(img, big)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src = Image.open(sys.argv[1]).convert('RGBA')
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    builders = {'teoria': fifths, 'pratica': pick, 'repertorio': vinyl}
    for name, color in COLORS.items():
        img = recolor(src, *color) if color else src.copy()
        builders[name](img).save(out / f'logo-{name}.png', optimize=True)
        print(out / f'logo-{name}.png')


if __name__ == '__main__':
    main()
