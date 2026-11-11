// Operator run control from the dashboard, persisted in DATA_DIR/control.json so a restart keeps the
// operator's choices:
//  - PLAY / STOP: STOP pauses new entries (open positions are still managed and exited).
//  - Kill-switch override (ON unless switched off; paper and live alike): the automatic loss brakes that would
//    halt trading (daily loss kill, weekly loss pause, perps and setups daily loss halts, and the model-health
//    halt, which is itself off unless MODEL_HEALTH_HALT=true) no longer stop it. Paper only: an exhausted paper
//    cash pool is refilled as a new training epoch (bot/training/supervisor.ts).

import fs from 'fs';
import path from 'path';

interface ControlState { active: boolean; ts: number; by?: string; killOverride?: boolean; overrideTs?: number }

export class RunControl {
  private state: ControlState;

  constructor(private readonly file: string) {
    try { this.state = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { this.state = { active: true, ts: 0 }; }
  }

  get active(): boolean { return this.state.active !== false; }

  /** Kill-switch override (default ON), paper and live alike (bot/engine.ts overrideActive has no mode check). */
  get killOverride(): boolean { return this.state.killOverride !== false; }

  set(active: boolean, by = 'dashboard'): void {
    this.state = { ...this.state, active, ts: Date.now(), by };
    this.save();
  }

  setOverride(on: boolean): void {
    this.state = { ...this.state, killOverride: on, overrideTs: Date.now() };
    this.save();
  }

  status(): { active: boolean; since: number | null; killOverride: boolean; overrideSince: number | null } {
    return { active: this.active, since: this.state.ts || null, killOverride: this.killOverride, overrideSince: this.state.overrideTs ?? null };
  }

  private save(): void {
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const tmp = `${this.file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this.state));
    fs.renameSync(tmp, this.file);
  }
}
