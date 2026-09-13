/**
 * Crash versus avoidance, side by side on one clock.
 *
 * Positions come from the simulation at one-second samples (a windowed
 * visualization bundle around the strike). Motion between samples is linearly
 * interpolated for display -- about a metre of chord error at orbital speed --
 * and the moment of closest approach is an exact sample. The explosion and its
 * debris cloud are illustrative: the two-body simulation does not model what a
 * collision breaks into, and the caption says so.
 */
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { api } from "../api";
import type { OptionRow, VisualizationBundle } from "../contracts";
import { versionsOf } from "../contracts";
import { disposeScene, makeSatellite } from "../scene/satellite";
import { clockText, distance } from "../workspace";

const CONTACT_M = 25;
const BEFORE_S = 40;
const AFTER_S = 20;

interface Loaded {
  bundle: VisualizationBundle;
  debrisId: string;
  strikeTca: number;
  strikeMissM: number;
  closingKms: number;
  avoid: OptionRow;
  avoidClosestM: number;
  avoidAtStrikeM: number;
}

interface Clock {
  t: number;
  generation: number;
}

/** Linear interpolation between the two samples around ``t``; metres. */
function positionAt(bundle: VisualizationBundle, variant: number, id: string, t: number) {
  const ts = bundle.t_s;
  let lo = 0,
    hi = ts.length - 1;
  if (t <= ts[0]) hi = 0;
  else if (t >= ts[hi]) lo = hi;
  else
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (ts[mid] <= t) lo = mid;
      else hi = mid;
    }
  const a = bundle.variants[variant].positions_m[id][lo];
  const b = bundle.variants[variant].positions_m[id][hi];
  const f = hi === lo ? 0 : (t - ts[lo]) / (ts[hi] - ts[lo]);
  // Simulation XYZ -> display X,Z,-Y, as in the main scene; kilometres.
  return new THREE.Vector3(
    (a[0] + (b[0] - a[0]) * f) / 1000,
    (a[2] + (b[2] - a[2]) * f) / 1000,
    -(a[1] + (b[1] - a[1]) * f) / 1000,
  );
}

function ReplayPane({
  data,
  variant,
  crash,
  clock,
  title,
  subtitle,
}: {
  data: Loaded;
  variant: number;
  crash: boolean;
  clock: React.MutableRefObject<Clock>;
  title: string;
  subtitle: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLDivElement>(null);
  const banner = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      element.textContent = "3D is unavailable on this device.";
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    element.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.0005, 5000);
    scene.add(new THREE.HemisphereLight("#d9ecff", "#20262c", 2.4));
    const sun = new THREE.DirectionalLight("#fff3d5", 3.2);
    sun.position.set(3, 5, 4);
    scene.add(sun);

    const satellite = makeSatellite();
    scene.add(satellite);
    const debris = new THREE.Mesh(
      new THREE.IcosahedronGeometry(1, 0),
      new THREE.MeshStandardMaterial({ color: "#a39b90", metalness: 0.7, roughness: 0.5 }),
    );
    scene.add(debris);
    const lineGeometry = new THREE.BufferGeometry().setAttribute(
      "position",
      new THREE.Float32BufferAttribute(new Float32Array(6), 3),
    );
    const lineMaterial = new THREE.LineBasicMaterial({ color: "#a1d5be" });
    const line = new THREE.Line(lineGeometry, lineMaterial);
    scene.add(line);

    const flash = new THREE.Mesh(
      new THREE.SphereGeometry(1, 24, 16),
      // No depth writes: a fading sphere would otherwise hide the fragments inside it.
      new THREE.MeshBasicMaterial({ color: "#ffd9a0", transparent: true, opacity: 0, depthWrite: false }),
    );
    scene.add(flash);
    const fragmentCount = 260;
    const fragmentGeometry = new THREE.BufferGeometry();
    const fragmentPositions = new Float32Array(fragmentCount * 3);
    fragmentGeometry.setAttribute("position", new THREE.BufferAttribute(fragmentPositions, 3));
    const fragments = new THREE.Points(
      fragmentGeometry,
      new THREE.PointsMaterial({ color: "#ffb27a", size: 4, sizeAttenuation: false }),
    );
    fragments.visible = false;
    // Positions change every frame; the bounding sphere computed at creation is a point.
    fragments.frustumCulled = false;
    scene.add(fragments);
    // Illustrative spread: directions on a sphere, speeds up to a few hundred m/s.
    const velocities = Array.from({ length: fragmentCount }, () => {
      const v = new THREE.Vector3().randomDirection();
      return v.multiplyScalar(0.02 + Math.random() * 0.3);
    });

    // One viewing direction for the whole replay: side-on to the approach.
    const start = data.strikeTca - BEFORE_S;
    const approach = positionAt(data.bundle, variant, data.debrisId, start)
      .sub(positionAt(data.bundle, variant, data.bundle.satellite_id, start))
      .normalize();
    const up = new THREE.Vector3(0, 1, 0);
    const side = approach.clone().cross(up);
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    side.normalize();

    let cameraDistance = 250;
    let seenGeneration = -1;
    let impact: THREE.Vector3 | null = null;

    const resize = () => {
      const { width, height } = element.getBoundingClientRect();
      renderer.setSize(width, height);
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();

    let frame = 0;
    const draw = () => {
      frame = requestAnimationFrame(draw);
      const { t, generation } = clock.current;
      if (generation !== seenGeneration) {
        seenGeneration = generation;
        impact = null;
        fragments.visible = false;
        satellite.visible = debris.visible = line.visible = true;
        flash.material.opacity = 0;
        if (banner.current) banner.current.hidden = true;
      }

      const sat = positionAt(data.bundle, variant, data.bundle.satellite_id, t);
      const deb = positionAt(data.bundle, variant, data.debrisId, t);
      const gapKm = sat.distanceTo(deb);

      if (crash && !impact && t >= data.strikeTca && data.strikeMissM < CONTACT_M) {
        impact = positionAt(data.bundle, variant, data.bundle.satellite_id, data.strikeTca)
          .add(positionAt(data.bundle, variant, data.debrisId, data.strikeTca))
          .multiplyScalar(0.5);
        satellite.visible = debris.visible = line.visible = false;
        fragments.visible = true;
        if (banner.current) banner.current.hidden = false;
      }

      let target: number;
      if (impact) {
        const since = Math.max(0, t - data.strikeTca);
        const radius = 0.32 * since + 0.004;
        for (let i = 0; i < fragmentCount; i++) {
          fragmentPositions[i * 3] = velocities[i].x * since;
          fragmentPositions[i * 3 + 1] = velocities[i].y * since;
          fragmentPositions[i * 3 + 2] = velocities[i].z * since;
        }
        fragmentGeometry.attributes.position.needsUpdate = true;
        const pulse = Math.min(1, since / 1.2);
        flash.scale.setScalar(0.02 + radius * 1.4 * pulse + 0.05 * pulse);
        flash.material.opacity = Math.max(0, 0.85 - pulse);
        flash.visible = flash.material.opacity > 0;
        target = Math.min(40, Math.max(0.35, radius * 3));
        if (readout.current) readout.current.textContent = "Contact";
      } else {
        const mid = sat.clone().add(deb).multiplyScalar(0.5);
        satellite.position.copy(sat.sub(mid));
        debris.position.copy(deb.sub(mid));
        const coordinates = lineGeometry.attributes.position as THREE.BufferAttribute;
        coordinates.setXYZ(0, satellite.position.x, satellite.position.y, satellite.position.z);
        coordinates.setXYZ(1, debris.position.x, debris.position.y, debris.position.z);
        coordinates.needsUpdate = true;
        lineGeometry.computeBoundingSphere();
        lineMaterial.color.set(gapKm * 1000 < data.bundle.min_separation_m ? "#eaa26f" : "#a1d5be");
        target = Math.min(300, Math.max(0.12, gapKm * 2.2));
        const [value, unit] = distance(gapKm * 1000);
        if (readout.current) readout.current.textContent = `${value} ${unit}`;
      }

      cameraDistance += (target - cameraDistance) * 0.12;
      satellite.scale.setScalar(cameraDistance * 0.02);
      debris.scale.setScalar(cameraDistance * 0.012);
      camera.position.copy(side).multiplyScalar(cameraDistance).addScaledVector(up, cameraDistance * 0.3);
      camera.near = cameraDistance / 500;
      camera.far = cameraDistance * 50;
      camera.updateProjectionMatrix();
      camera.lookAt(0, 0, 0);
      renderer.render(scene, camera);
    };
    draw();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      disposeScene(scene);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [data, variant, crash, clock]);

  return (
    <div className="replay-pane glass">
      <div className="replay-title">
        <strong>{title}</strong>
        <small>{subtitle}</small>
      </div>
      <div className="replay-canvas" ref={host} />
      <div className="replay-readout" ref={readout} />
      {crash && (
        <div className="replay-banner" ref={banner} hidden>
          Collision · debris cloud is illustrative
        </div>
      )}
    </div>
  );
}

export function CrashReplay() {
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState("");
  const [time, setTime] = useState(0);
  const clock = useRef<Clock>({ t: 0, generation: 0 });
  const playing = useRef(false);

  useEffect(() => {
    let live = true;
    (async () => {
      const snapshot = await api.createCase("collision");
      const versions = versionsOf(snapshot);
      const analysis = await api.analysis(snapshot.case_id, versions);
      const baseline = analysis.options.find((o) => o.kind === "NO_BURN");
      const strike = baseline?.primary_encounter;
      if (!strike) throw new Error("The collision scenario reported no strike.");
      const comfortable = snapshot.policy.min_separation_m * 1.25;
      const closest = (o: OptionRow) =>
        Math.min(...(o.validation?.encounters.map((e) => e.min_separation_m) ?? [Infinity]));
      const ranked = [...analysis.options].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99));
      const avoid =
        ranked.find((o) => o.validation?.status === "PASS" && o.kind !== "NO_BURN" && closest(o) >= comfortable) ??
        ranked.find((o) => o.candidate_id === analysis.recommended_id);
      if (!avoid) throw new Error("No verified avoidance option in this scenario.");
      const bundle = await api.visualizationWindow(
        snapshot.case_id,
        versions,
        ["baseline", avoid.candidate_id],
        Math.max(0, strike.tca_s - BEFORE_S),
        Math.min(snapshot.scenario.horizon_s, strike.tca_s + AFTER_S),
        1,
      );
      const debrisId = snapshot.scenario.primary_threat_id;
      const k = bundle.t_s.findIndex((t) => Math.abs(t - strike.tca_s) < 1e-3);
      const rel = (i: number) => {
        const s = bundle.variants[0].positions_m[bundle.satellite_id][i];
        const d = bundle.variants[0].positions_m[debrisId][i];
        return [d[0] - s[0], d[1] - s[1], d[2] - s[2]];
      };
      const before = rel(Math.max(0, k - 1)),
        after = rel(Math.min(bundle.t_s.length - 1, k + 1));
      const dt = bundle.t_s[Math.min(bundle.t_s.length - 1, k + 1)] - bundle.t_s[Math.max(0, k - 1)];
      const closingKms = Math.hypot(after[0] - before[0], after[1] - before[1], after[2] - before[2]) / dt / 1000;
      if (!live) return;
      clock.current = { t: bundle.t_s[0], generation: 1 };
      setData({
        bundle,
        debrisId,
        strikeTca: strike.tca_s,
        strikeMissM: strike.min_separation_m,
        closingKms,
        avoid,
        avoidClosestM: closest(avoid),
        avoidAtStrikeM: bundle.variants[1].pair_separations_m[debrisId][k],
      });
      playing.current = true;
    })().catch((reason) => live && setError(reason instanceof Error ? reason.message : "Replay failed."));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!data) return;
    let frame = 0,
      previous = performance.now(),
      lastShown = 0;
    const end = data.bundle.t_s[data.bundle.t_s.length - 1];
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      const elapsed = Math.min(0.1, (now - previous) / 1000);
      previous = now;
      if (!playing.current) return;
      // Fast far from the pass, slow through it, so the moment itself is visible.
      const speed = Math.min(15, Math.max(0.25, Math.abs(clock.current.t - data.strikeTca) / 2));
      clock.current.t = Math.min(end, clock.current.t + elapsed * speed);
      if (clock.current.t >= end) playing.current = false;
      if (now - lastShown > 80) {
        lastShown = now;
        setTime(clock.current.t);
      }
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [data]);

  const replay = () => {
    if (!data) return;
    clock.current = { t: data.bundle.t_s[0], generation: clock.current.generation + 1 };
    playing.current = true;
  };

  if (error) return <p className="exchange-error">{error}</p>;
  if (!data)
    return (
      <div className="loading-card glass">
        <span className="loading-orbit" />
        <p>Loading the collision scenario and computing both trajectories at one-second steps.</p>
      </div>
    );

  const toStrike = data.strikeTca - time;
  const burn = `${data.avoid.delta_v_mps.toFixed(2)} m/s ${
    data.avoid.direction === "PROGRADE" ? "speed up" : "slow down"
  } at T+${clockText(data.avoid.burn_t_s ?? 0).slice(0, 5)}`;
  const [strikeValue, strikeUnit] = distance(data.strikeMissM);
  const [avoidValue, avoidUnit] = distance(data.avoidAtStrikeM);
  const [closestValue, closestUnit] = distance(data.avoidClosestM);

  return (
    <>
      <p className="dialog-intro">
        Same satellite, same piece of debris, same clock. On the left nobody
        acts. On the right the burn the independent verifier cleared was made
        hours earlier.
      </p>
      <div className="replay-clock">
        <span>SIMULATION CLOCK</span>
        <strong>T+ {clockText(time)}</strong>
        <small>
          {toStrike > 0.05 ? `${toStrike.toFixed(1)} s to closest approach` : "closest approach reached"}
        </small>
        <button className="subtle-button" onClick={replay}>
          Replay
        </button>
      </div>
      <div className="replay-grid">
        <ReplayPane
          data={data}
          variant={0}
          crash
          clock={clock}
          title="Do nothing"
          subtitle="Original trajectory"
        />
        <ReplayPane
          data={data}
          variant={1}
          crash={false}
          clock={clock}
          title="With the verified burn"
          subtitle={burn}
        />
      </div>
      <div className="replay-facts">
        <p>
          <strong>Left:</strong> at T+{clockText(data.strikeTca)} the centres pass{" "}
          <strong>
            {strikeValue} {strikeUnit}
          </strong>{" "}
          apart, closing at {data.closingKms.toFixed(1)} km/s. Both objects are
          metres across, so that is a collision.
        </p>
        <p>
          <strong>Right:</strong> at the same instant they are{" "}
          <strong>
            {avoidValue} {avoidUnit}
          </strong>{" "}
          apart. Over the whole six hours this burn never comes closer than{" "}
          {closestValue} {closestUnit} to anything — above the{" "}
          {distance(data.bundle.min_separation_m).join(" ")} clearance floor,
          checked by the independent verifier against every object.
        </p>
      </div>
      <p className="caption">
        Positions are the simulation&rsquo;s one-second samples; motion between
        samples is interpolated for display and the closest approach is an exact
        sample. Playback slows near the pass. Models are enlarged. The
        explosion and debris cloud are illustrative — the simulation does not
        model what a collision breaks into. Synthetic scenario: the satellite
        orbit is seeded from NOAA 20; the debris object is constructed.
      </p>
    </>
  );
}
