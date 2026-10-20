import { Injectable } from '@nestjs/common';

type Labels = Record<string, string>;

interface Series {
  labels: Labels;
  value: number;
}

/**
 * Registre de métriques minimal, format d'exposition Prometheus.
 * Pas de dépendance externe (prom-client) : l'offre Alwaysdata est petite
 * en disque, on évite 2 Mo de node_modules pour 4 compteurs.
 */
@Injectable()
export class MetricsRegistry {
  private counters = new Map<string, Series>();
  private timers = new Map<string, { labels: Labels; sum: number; count: number }>();

  private key(name: string, labels: Labels): string {
    const entries = Object.entries(labels).sort(([a], [b]) => a.localeCompare(b));
    return `${name}|${entries.map(([k, v]) => `${k}=${v}`).join(',')}`;
  }

  inc(name: string, labels: Labels = {}, value = 1): void {
    const k = this.key(name, labels);
    const cur = this.counters.get(k);
    if (cur) cur.value += value;
    else this.counters.set(k, { labels, value });
  }

  observe(name: string, value: number, labels: Labels = {}): void {
    const k = this.key(name, labels);
    const cur = this.timers.get(k);
    if (cur) {
      cur.sum += value;
      cur.count += 1;
    } else {
      this.timers.set(k, { labels, sum: value, count: 1 });
    }
  }

  private renderLabels(labels: Labels): string {
    const entries = Object.entries(labels);
    if (!entries.length) return '';
    return `{${entries.map(([k, v]) => `${k}="${String(v).replace(/"/g, '')}"`).join(',')}}`;
  }

  render(): string {
    const lines: string[] = [];
    const counterNames = new Set([...this.counters.values()].map((s) => s.labels));
    void counterNames;

    const grouped = new Map<string, Series[]>();
    for (const [k, s] of this.counters) {
      const name = k.split('|')[0];
      if (!grouped.has(name)) grouped.set(name, []);
      grouped.get(name)!.push(s);
    }
    for (const [name, series] of grouped) {
      lines.push(`# HELP ${name} Compteur applicatif`);
      lines.push(`# TYPE ${name} counter`);
      for (const s of series) lines.push(`${name}${this.renderLabels(s.labels)} ${s.value}`);
    }

    const timers = new Map<string, { labels: Labels; sum: number; count: number }[]>();
    for (const [k, t] of this.timers) {
      const name = k.split('|')[0];
      if (!timers.has(name)) timers.set(name, []);
      timers.get(name)!.push(t);
    }
    for (const [name, series] of timers) {
      lines.push(`# HELP ${name} Durée cumulée en millisecondes`);
      lines.push(`# TYPE ${name} summary`);
      for (const t of series) {
        const l = this.renderLabels(t.labels);
        lines.push(`${name}_sum${l} ${t.sum}`);
        lines.push(`${name}_count${l} ${t.count}`);
      }
    }

    return lines.join('\n') + '\n';
  }
}
