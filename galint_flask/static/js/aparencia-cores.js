// Aparência (Configurações → Aparência): seletor de cores no estilo do Windows (roda, brilho, RGB/HSV
// e hex) e prévia ao vivo. Trazido do Pipocas do Biel (pipoca/static/seletor-cores.js) em 21/11/2026,
// com a mesma lógica: os tons derivados vêm do servidor (previa.json), a mesma conta do tema.css.
(() => {
  'use strict';
  const form = document.getElementById('skin-editor');
  if (!form) return;

  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
  const toHex = (rgb) => `#${rgb.map((c) => Math.round(clamp(c, 0, 255)).toString(16).padStart(2, '0')).join('')}`;
  const parseHex = (text) => {
    const match = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec((text || '').trim());
    if (!match) return null;
    const digits = match[1].length === 3 ? match[1].replace(/./g, '$&$&') : match[1];
    return [0, 2, 4].map((i) => parseInt(digits.slice(i, i + 2), 16));
  };
  // HSV: matiz 0–360, saturação e brilho 0–1.
  const hsvToRgb = (hue, sat, value) => [5, 3, 1].map((n) => {
    const k = (n + hue / 60) % 6;
    return (value - value * sat * Math.max(0, Math.min(k, 4 - k, 1))) * 255;
  });
  const rgbToHsv = ([r, g, b]) => {
    const [rr, gg, bb] = [r / 255, g / 255, b / 255];
    const max = Math.max(rr, gg, bb);
    const delta = max - Math.min(rr, gg, bb);
    let hue = 0;
    if (delta) {
      if (max === rr) hue = ((gg - bb) / delta) % 6;
      else if (max === gg) hue = (bb - rr) / delta + 2;
      else hue = (rr - gg) / delta + 4;
    }
    return [(hue * 60 + 360) % 360, max ? delta / max : 0, max];
  };
  // Distância ponderada pela visão ("redmean", a mesma do servidor).
  const distance = (a, b) => {
    const red = (a[0] + b[0]) / 2;
    const [dr, dg, db] = [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    return Math.sqrt((2 + red / 256) * dr * dr + 4 * dg * dg + (2 + (255 - red) / 256) * db * db);
  };

  // Nome da cor mais próxima (como o "Rose" do Windows): as paletas da tela e cores comuns.
  const COMMON = [
    ['Branco', '#ffffff'], ['Gelo', '#eef1f4'], ['Prata', '#c0c0c0'], ['Cinza', '#808080'], ['Chumbo', '#4b4f54'],
    ['Preto', '#000000'], ['Vermelho', '#e01b24'], ['Carmim', '#a0001c'], ['Vinho', '#6d1f2f'], ['Coral', '#ff7f50'],
    ['Rosa', '#ffc0cb'], ['Rosa-chiclete', '#ff69b4'], ['Magenta', '#ff00ff'], ['Fúcsia', '#c71585'], ['Pêssego', '#ffdab9'],
    ['Laranja', '#ff8c00'], ['Tangerina', '#f28500'], ['Caramelo', '#c68e17'], ['Marrom', '#8b4513'], ['Chocolate', '#5c3317'],
    ['Bege', '#f5f5dc'], ['Creme', '#fffdd0'], ['Amarelo', '#ffff00'], ['Dourado', '#ffd700'], ['Mostarda', '#e1ad01'],
    ['Limão', '#dfff4f'], ['Verde-limão', '#32cd32'], ['Verde', '#008000'], ['Verde-folha', '#4caf50'],
    ['Verde-escuro', '#006400'], ['Oliva', '#808000'], ['Esmeralda', '#50c878'], ['Ciano', '#00ffff'],
    ['Azul-petróleo', '#005f6a'], ['Azul-celeste', '#87ceeb'], ['Azul-bebê', '#a1caf1'], ['Azul', '#0000ff'],
    ['Azul-royal', '#4169e1'], ['Azul-marinho', '#000080'], ['Anil', '#4b0082'], ['Violeta', '#8f00ff'], ['Roxo', '#800080'],
    ['Ametista', '#9966cc'], ['Orquídea', '#da70d6'], ['Uva', '#6f2da8'],
  ];
  const swatches = [...form.querySelectorAll('.swatch')];
  const names = swatches.map((s) => [s.dataset.name, s.dataset.color]).concat(COMMON)
    .map(([name, hex]) => [name, parseHex(hex)]);
  const nameOf = (rgb) => names.reduce((best, item) => (distance(item[1], rgb) < distance(best[1], rgb) ? item : best))[0];

  // ---------- seletor ----------
  const box = document.getElementById('color-picker');
  const canvas = box.querySelector('canvas');
  const marker = box.querySelector('.picker-marker');
  const tip = box.querySelector('.picker-name');
  const sample = box.querySelector('.picker-preview');
  const slider = box.querySelector('.picker-brightness input');
  const mode = box.querySelector('.picker-mode');
  const hexField = box.querySelector('.picker-hex');
  const channels = [...box.querySelectorAll('.picker-channels input')];
  const channelLabels = [...box.querySelectorAll('.picker-channels span')];
  const context = canvas.getContext('2d');
  let hsv = [0, 0, 1];
  let wheel = null; // roda com brilho máximo; os outros brilhos só escurecem estes pixels
  let drawn = -1;
  let dragging = false;
  let listener = () => {};

  const buildWheel = () => {
    const ratio = window.devicePixelRatio || 1;
    const size = Math.round((canvas.getBoundingClientRect().width || 220) * ratio);
    if (wheel && canvas.width === size) return;
    canvas.width = canvas.height = size;
    const radius = size / 2;
    wheel = new Uint8ClampedArray(size * size * 4);
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        const dx = x + 0.5 - radius;
        const dy = y + 0.5 - radius;
        const dist = Math.hypot(dx, dy);
        const alpha = clamp(radius - dist, 0, 1); // borda suavizada
        if (alpha) {
          const rgb = hsvToRgb((Math.atan2(-dy, dx) * 180 / Math.PI + 360) % 360, Math.min(1, dist / radius), 1);
          const i = (y * size + x) * 4;
          wheel.set([rgb[0], rgb[1], rgb[2], alpha * 255], i);
        }
      }
    }
    drawn = -1;
  };
  const drawWheel = () => {
    if (drawn === hsv[2]) return;
    const image = context.createImageData(canvas.width, canvas.height);
    for (let i = 0; i < wheel.length; i += 4) {
      image.data[i] = wheel[i] * hsv[2];
      image.data[i + 1] = wheel[i + 1] * hsv[2];
      image.data[i + 2] = wheel[i + 2] * hsv[2];
      image.data[i + 3] = wheel[i + 3];
    }
    context.putImageData(image, 0, 0);
    drawn = hsv[2];
  };
  const fillChannels = () => {
    const values = mode.value === 'hsv'
      ? [Math.round(hsv[0]) % 360, Math.round(hsv[1] * 100), Math.round(hsv[2] * 100)]
      : hsvToRgb(...hsv).map(Math.round);
    channels.forEach((input, i) => { input.value = values[i]; });
  };
  const render = (source) => {
    const rgb = hsvToRgb(...hsv);
    const hex = toHex(rgb);
    drawWheel();
    const angle = hsv[0] * Math.PI / 180;
    const left = `${50 + 50 * hsv[1] * Math.cos(angle)}%`;
    const top = `${50 - 50 * hsv[1] * Math.sin(angle)}%`;
    [marker, tip].forEach((el) => { el.style.left = left; el.style.top = top; });
    marker.style.backgroundColor = hex;
    sample.style.backgroundColor = hex;
    slider.style.setProperty('--picker-full', toHex(hsvToRgb(hsv[0], hsv[1], 1)));
    tip.textContent = nameOf(rgb);
    if (source !== 'slider') slider.value = Math.round(hsv[2] * 100);
    if (source !== 'hex') hexField.value = hex.toUpperCase();
    if (source !== 'channels') fillChannels();
    return hex;
  };
  const changed = (source) => listener(render(source));
  // Preto e cinzas não têm matiz: mantém o da cor anterior para o marcador não pular.
  const fromRgb = (rgb) => {
    const next = rgbToHsv(rgb);
    if (next[2] === 0) return [hsv[0], hsv[1], 0];
    if (next[1] === 0) return [hsv[0], 0, next[2]];
    return next;
  };

  const pickAt = (event) => {
    const rect = canvas.getBoundingClientRect();
    const dx = event.clientX - rect.left - rect.width / 2;
    const dy = event.clientY - rect.top - rect.height / 2;
    hsv = [(Math.atan2(-dy, dx) * 180 / Math.PI + 360) % 360, Math.min(1, Math.hypot(dx, dy) / (rect.width / 2)), hsv[2]];
    changed();
  };
  canvas.addEventListener('pointerdown', (event) => {
    dragging = true;
    canvas.setPointerCapture(event.pointerId);
    box.classList.add('naming');
    pickAt(event);
  });
  canvas.addEventListener('pointermove', (event) => { if (dragging) pickAt(event); });
  const release = () => { dragging = false; box.classList.remove('naming'); };
  canvas.addEventListener('pointerup', release);
  canvas.addEventListener('pointercancel', release);
  canvas.addEventListener('pointerenter', () => box.classList.add('naming'));
  canvas.addEventListener('pointerleave', () => { if (!dragging) box.classList.remove('naming'); });
  canvas.addEventListener('focus', () => box.classList.add('naming'));
  canvas.addEventListener('blur', () => box.classList.remove('naming'));
  canvas.addEventListener('keydown', (event) => {
    const step = event.shiftKey ? 10 : 2;
    const move = {ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step]}[event.key];
    if (!move) return;
    event.preventDefault();
    hsv = [(hsv[0] + move[0] + 360) % 360, clamp(hsv[1] + move[1] / 100, 0, 1), hsv[2]];
    changed();
  });
  slider.addEventListener('input', () => {
    hsv = [hsv[0], hsv[1], Number(slider.value) / 100];
    changed('slider');
  });
  mode.addEventListener('change', () => {
    const hsvMode = mode.value === 'hsv';
    (hsvMode ? ['Matiz', 'Saturação', 'Brilho'] : ['Vermelho', 'Verde', 'Azul'])
      .forEach((label, i) => { channelLabels[i].textContent = label; });
    (hsvMode ? [359, 100, 100] : [255, 255, 255]).forEach((max, i) => { channels[i].max = max; });
    fillChannels();
  });
  hexField.addEventListener('input', () => {
    const rgb = parseHex(hexField.value);
    if (rgb && hexField.value.replace('#', '').trim().length === 6) {
      hsv = fromRgb(rgb);
      changed('hex');
    }
  });
  hexField.addEventListener('change', () => {
    const rgb = parseHex(hexField.value);
    if (rgb) {
      hsv = fromRgb(rgb);
      changed();
    } else {
      render();
    }
  });
  channels.forEach((input) => {
    input.addEventListener('input', () => {
      const values = channels.map((field) => (field.value === '' ? NaN : Number(field.value)));
      if (values.some((v) => !Number.isFinite(v))) return;
      hsv = mode.value === 'hsv'
        ? [clamp(values[0], 0, 359), clamp(values[1], 0, 100) / 100, clamp(values[2], 0, 100) / 100]
        : fromRgb(values.map((v) => clamp(v, 0, 255)));
      changed('channels');
    });
    input.addEventListener('change', fillChannels);
  });
  let resizing = 0;
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizing);
    resizing = requestAnimationFrame(() => { buildWheel(); render(); });
  });
  const picker = {
    set(hex) {
      const rgb = parseHex(hex);
      if (rgb) {
        hsv = fromRgb(rgb);
        render();
      }
    },
    onChange(callback) { listener = callback; },
  };
  buildWheel();

  // ---------- skin ----------
  const root = document.documentElement;
  const targets = [...form.querySelectorAll('.skin-target')];
  const fields = Object.fromEntries(targets.map((button) => [button.dataset.target, form.elements.namedItem(button.dataset.target)]));
  const errorsBox = document.getElementById('skin-errors');
  const warningsBox = document.getElementById('skin-warnings');
  const save = document.getElementById('skin-save');
  let active = targets[0].dataset.target;
  let dirty = false;
  let queued = null;
  let busy = false;

  const show = (box, messages) => {
    box.textContent = messages.join(' ');
    box.hidden = !messages.length;
  };
  const send = () => {
    const query = new URLSearchParams(queued);
    queued = null;
    busy = true;
    fetch(`${form.dataset.preview}?${query}`, {credentials: 'same-origin', headers: {Accept: 'application/json'}})
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((data) => {
        // Com erro (fundo ou menu claro demais), a tela fica na última prévia válida e só mostra o aviso.
        if (!data.errors.length) Object.entries(data.variables).forEach(([name, value]) => root.style.setProperty(name, value));
        show(errorsBox, data.errors);
        show(warningsBox, data.warnings);
        save.disabled = data.errors.length > 0;
      })
      .catch(() => {})
      .finally(() => {
        busy = false;
        if (queued) send();
      });
  };
  const preview = () => {
    queued = Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, input.value]));
    if (!busy) send();
  };
  const showTarget = (key) => {
    const button = targets.find((b) => b.dataset.target === key);
    const hex = fields[key].value;
    button.querySelector('rect').setAttribute('fill', hex);
    button.querySelector('small').textContent = `${nameOf(parseHex(hex))} · ${hex.toUpperCase()}`;
  };
  const presets = [...form.querySelectorAll('.skin-preset')];
  const markPresets = () => presets.forEach((button) => {
    button.setAttribute('aria-pressed', String(Object.keys(fields).every((key) => button.dataset[key] === fields[key].value)));
  });
  const markSwatches = () => {
    swatches.forEach((s) => s.setAttribute('aria-pressed', String(s.dataset.color === fields[active].value)));
  };
  const setColor = (key, hex, fromPicker) => {
    if (fields[key].value === hex) return;
    fields[key].value = hex;
    showTarget(key);
    if (key === active) {
      if (!fromPicker) picker.set(hex);
      markSwatches();
    }
    markPresets();
    dirty = true;
    preview();
  };
  const select = (key, focus) => {
    active = key;
    targets.forEach((button) => {
      const on = button.dataset.target === key;
      button.setAttribute('aria-checked', String(on));
      button.tabIndex = on ? 0 : -1;
      if (on && focus) button.focus();
    });
    picker.set(fields[key].value);
    markSwatches();
  };

  targets.forEach((button, index) => {
    button.addEventListener('click', () => select(button.dataset.target));
    button.addEventListener('keydown', (event) => {
      const delta = {ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1}[event.key];
      if (!delta) return;
      event.preventDefault();
      select(targets[(index + delta + targets.length) % targets.length].dataset.target, true);
    });
  });
  swatches.forEach((s) => s.addEventListener('click', () => setColor(active, s.dataset.color)));
  presets.forEach((button) => button.addEventListener('click', () => {
    Object.keys(fields).forEach((key) => setColor(key, button.dataset[key]));
  }));
  picker.onChange((hex) => setColor(active, hex, true));
  window.addEventListener('beforeunload', (event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = '';
  });
  form.addEventListener('submit', () => { dirty = false; });
  Object.keys(fields).forEach(showTarget);
  select(active);
})();
