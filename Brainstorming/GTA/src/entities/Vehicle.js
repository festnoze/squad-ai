/**
 * Drivable vehicle.
 *
 * Physics is Rapier's `DynamicRayCastVehicleController`: a dynamic chassis body with four
 * raycast wheels providing suspension, traction and lateral grip. That is the same model
 * used by most driving games - far more stable than four real cylinder colliders, and it
 * lets us tune handling directly (grip, suspension, engine force) rather than fighting a
 * contact solver.
 *
 * On top of it sits a small drivetrain sim: an engine torque curve, a 6-speed automatic
 * box, speed-sensitive steering, and a handbrake that unloads the rear grip so the car
 * will actually slide.
 */

import { Vector3, Quaternion, MathUtils } from 'three/webgpu';
import { createVehicleMesh, addLightbar, VEHICLE_CLASSES, TRAFFIC_COLOURS } from './VehicleMesh.js';
import { GROUP, groups, RAPIER } from '../physics/Physics.js';

const GEAR_RATIOS = [3.4, 2.1, 1.5, 1.15, 0.92, 0.76];
const FINAL_DRIVE = 3.6;
const SHIFT_UP_RPM = 6400;
const SHIFT_DOWN_RPM = 2600;
const IDLE_RPM = 850;
const MAX_RPM = 7200;

/** Torque multiplier across the rev range - peaky enough to be worth shifting for. */
function torqueCurve(rpm) {
  const t = MathUtils.clamp(rpm / MAX_RPM, 0, 1);
  // Rises to a plateau around 60-80% of redline, falls off after.
  return MathUtils.clamp(0.45 + 1.35 * t - 1.0 * t * t, 0.2, 1.0);
}

export class Vehicle {
  static _nextId = 0;

  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {object} opts
   */
  constructor(physics, {
    className = 'sedan',
    position = new Vector3(),
    heading = 0,
    colour = null,
    livery = null,
  } = {}) {
    this.physics = physics;
    this.className = className;
    this.spec = VEHICLE_CLASSES[className];
    this.livery = livery;
    this.colour = colour ?? TRAFFIC_COLOURS[Math.floor(Math.random() * TRAFFIC_COLOURS.length)];

    const visual = createVehicleMesh(className, this.colour);
    this.group = visual.group;
    this.wheelObjects = visual.wheels;
    this.headlights = visual.headlights;
    this.taillights = visual.taillights;
    this.detailParts = visual.details;
    /** Current LOD tier: 0 = full, 1 = no lamps, 2 = body only. */
    this.lod = 0;
    // The lightbar is authored in ground space like the body, so it rides on the shell.
    this.lightbar = livery === 'police' ? addLightbar(visual.shell, this.spec) : null;

    /* ------------------------------------------------------------------ chassis */
    const c = this.spec.chassis;
    const bodyDesc = RAPIER.RigidBodyDesc.dynamic()
      .setTranslation(position.x, position.y, position.z)
      .setRotation(yawQuat(heading))
      .setLinearDamping(0.08)
      .setAngularDamping(0.6)
      .setCcdEnabled(true);
    this.body = physics.world.createRigidBody(bodyDesc);

    const colliderDesc = RAPIER.ColliderDesc.cuboid(c.hx, c.hy, c.hz)
      // Centre of mass sits low: this is what stops a raycast car rolling over in corners.
      .setTranslation(0, c.hy * 0.35, 0)
      .setCollisionGroups(groups(GROUP.VEHICLE))
      .setActiveEvents(RAPIER.ActiveEvents.COLLISION_EVENTS)
      .setFriction(0.4)
      .setRestitution(0.1)
      .setMass(this.spec.mass);
    this.collider = physics.world.createCollider(colliderDesc, this.body);
    physics.owners.set(this.collider.handle, this);

    /* ------------------------------------------------------------------- wheels */
    this.controller = physics.createVehicleController(this.body);
    this.controller.indexUpAxis = 1;
    this.controller.setIndexForwardAxis = 2;

    const { track, wheelbase, wheelRadius } = this.spec;
    const suspensionRest = 0.32;
    const down = { x: 0, y: -1, z: 0 };
    const axle = { x: -1, y: 0, z: 0 };
    // Order: FL, FR, RL, RR.
    this.wheelPositions = [
      { x: -track, y: c.hy * 0.1, z: wheelbase },
      { x: track, y: c.hy * 0.1, z: wheelbase },
      { x: -track, y: c.hy * 0.1, z: -wheelbase },
      { x: track, y: c.hy * 0.1, z: -wheelbase },
    ];
    for (const p of this.wheelPositions) {
      this.controller.addWheel(p, down, axle, suspensionRest, wheelRadius);
    }
    for (let i = 0; i < 4; i++) {
      this.controller.setWheelSuspensionStiffness(i, 34);
      this.controller.setWheelSuspensionCompression(i, 0.85);
      this.controller.setWheelSuspensionRelaxation(i, 0.95);
      this.controller.setWheelMaxSuspensionTravel(i, 0.28);
      this.controller.setWheelMaxSuspensionForce(i, 60000);
      // Rear tyres slightly looser than fronts: mild, controllable oversteer.
      this.controller.setWheelFrictionSlip(i, i < 2 ? 2.6 : 2.35);
      this.controller.setWheelSideFrictionStiffness(i, 1.0);
    }

    /* -------------------------------------------------------------------- state */
    this.throttle = 0;
    this.brake = 0;
    this.steer = 0;
    this.handbrake = false;
    this.gear = 1;
    this.rpm = IDLE_RPM;
    this.speed = 0;
    this.reverse = false;
    this.engineOn = true;
    this.headlightsOn = false;
    this.health = 100;
    this.occupied = false;
    this._shiftCooldown = 0;
    this._steerInput = 0;
    this._sirenPhase = 0;

    /** Per-wheel slip 0..1, filled each step; drives skid marks and tyre smoke. */
    this.wheelSlip = [0, 0, 0, 0];
    /** Per-wheel world contact points, or null when airborne. */
    this.wheelContacts = [null, null, null, null];
    /** Damage accumulator; paint darkens and the engine smokes as it climbs. */
    this.damage = 0;
    this._paintCloned = false;
    this._id = Vehicle._nextId++;

    this._pos = new Vector3();
    this._quat = new Quaternion();
    this._forward = new Vector3();
    this._right = new Vector3();
    this._vel = new Vector3();

    this.group.position.copy(position);
    this.group.quaternion.copy(yawQuatThree(heading));
  }

  /** Half-length used for proximity checks; boats expose the same property. */
  get enterRadius() { return this.spec.chassis.hz; }

  /** World position (chassis centre). */
  get position() {
    const t = this.body.translation();
    return this._pos.set(t.x, t.y, t.z);
  }

  get speedKmh() { return Math.abs(this.speed) * 3.6; }

  get gearLabel() {
    if (this.reverse) return 'R';
    if (Math.abs(this.speed) < 0.4 && this.throttle < 0.05) return 'N';
    return String(this.gear);
  }

  /** Forward vector in world space. */
  forward(out = this._forward) {
    const r = this.body.rotation();
    this._quat.set(r.x, r.y, r.z, r.w);
    return out.set(0, 0, 1).applyQuaternion(this._quat);
  }

  /** Heading angle in radians. */
  get heading() {
    this.forward(this._forward);
    return Math.atan2(this._forward.x, this._forward.z);
  }

  /**
   * Apply driver input for this step.
   * @param {object} input `{ throttle, brake, steer, handbrake }`, all -1..1 / 0..1
   */
  setInput({ throttle = 0, brake = 0, steer = 0, handbrake = false }) {
    this.throttle = MathUtils.clamp(throttle, 0, 1);
    this.brake = MathUtils.clamp(brake, 0, 1);
    this._steerInput = MathUtils.clamp(steer, -1, 1);
    this.handbrake = handbrake;
  }

  /** Fixed-step drivetrain and control update. Call before `physics.step()`. */
  fixedUpdate(dt) {
    /*
     * A parked car that Rapier has put to sleep needs no simulation at all: no drivetrain,
     * no suspension raycasts, no drag. Skipping it is the single biggest saving in the
     * frame, because a city has far more parked cars than moving ones. Rapier wakes the
     * body itself the moment anything touches it.
     */
    if (!this.occupied && this.body.isSleeping()) return;

    /*
     * Rapier force accumulators persist until reset (see the note in Boat.fixedUpdate).
     * Drag and downforce below would otherwise compound every single step.
     *
     * The `false` is load-bearing: that argument is `wakeUp`, and passing `true` here
     * woke every parked car in the city on every step, keeping all of them permanently
     * simulated. It cost ~40 ms a frame.
     */
    this.body.resetForces(false);
    this.body.resetTorques(false);

    const lv = this.body.linvel();
    this._vel.set(lv.x, lv.y, lv.z);
    this.forward(this._forward);
    this._right.set(1, 0, 0).applyQuaternion(this._quat);
    // Signed speed along the car's own forward axis.
    this.speed = this._vel.dot(this._forward);
    const absSpeed = Math.abs(this.speed);

    /* ------------------------------------------------------------------ steering */
    // Steering authority falls off with speed so the car is not twitchy at 150 km/h.
    const speedFactor = 1 / (1 + absSpeed * 0.055);
    const maxSteer = 0.58 * speedFactor;
    const target = this._steerInput * maxSteer;
    // Rate-limit rather than snap: gives the front end weight.
    const rate = (this.handbrake ? 6.5 : 4.2) * dt * (1 + speedFactor);
    this.steer = MathUtils.clamp(target, this.steer - rate, this.steer + rate);
    this.controller.setWheelSteering(0, this.steer);
    this.controller.setWheelSteering(1, this.steer);

    /* --------------------------------------------------------------- drivetrain */
    const wheelCircumference = 2 * Math.PI * this.spec.wheelRadius;
    const wheelRps = absSpeed / wheelCircumference;
    const ratio = GEAR_RATIOS[this.gear - 1] * FINAL_DRIVE;
    this.rpm = MathUtils.clamp(wheelRps * ratio * 60, IDLE_RPM, MAX_RPM);
    if (this.throttle > 0.05 && absSpeed < 1) this.rpm = Math.max(this.rpm, 1800 + this.throttle * 2200);

    this._shiftCooldown = Math.max(0, this._shiftCooldown - dt);
    if (this._shiftCooldown === 0 && !this.reverse) {
      if (this.rpm > SHIFT_UP_RPM && this.gear < GEAR_RATIOS.length) {
        this.gear++; this._shiftCooldown = 0.35;
      } else if (this.rpm < SHIFT_DOWN_RPM && this.gear > 1) {
        this.gear--; this._shiftCooldown = 0.3;
      }
    }

    // Reverse engages from a near stop when braking with no forward motion.
    if (this.speed < 0.6 && this.brake > 0.5 && this.throttle < 0.1) this.reverse = true;
    if (this.speed > 0.6 || this.throttle > 0.5) this.reverse = false;

    /* -------------------------------------------------------- engine and brakes */
    let engineForce = 0;
    let brakeForce = 0;

    if (this.reverse) {
      engineForce = -this.brake * this.spec.power * 0.45;
      brakeForce = this.throttle * 55;
    } else {
      const curve = torqueCurve(this.rpm);
      const gearMul = GEAR_RATIOS[this.gear - 1] / GEAR_RATIOS[0];
      engineForce = this.throttle * this.spec.power * curve * (0.55 + gearMul * 0.45);
      // Cut power at the class top speed instead of letting drag alone limit it.
      if (this.speed > this.spec.topSpeed) engineForce *= 0.05;
      brakeForce = this.brake * 90;
    }
    // Engine braking when coasting.
    if (this.throttle < 0.02 && this.brake < 0.02 && absSpeed > 0.5) brakeForce = 6;

    /*
     * Handbrake drifting.
     *
     * The naive version - full brake plus no rear grip - just stops the car: the locked
     * rear axle scrubs off all the speed while the fronts still grip, so the car rotates
     * once and halts. A drift needs the rear tyres to be *spinning free of lateral grip*,
     * not stopped, so the handbrake brake force is scaled away as the throttle comes in.
     * Flooring it mid-handbrake therefore holds the slide, which is how a power slide
     * actually works.
     */
    const slideThrottle = this.handbrake ? this.throttle : 0;
    const handbrakeForce = 62 * (1 - slideThrottle * 0.92);
    // The front axle also gives up a little grip while sliding, or the nose bites and
    // snaps the car straight the instant the rear steps out.
    const frontGrip = this.handbrake ? 1.7 : 2.6;
    const rearGrip = this.handbrake ? 0.42 : 2.35;

    const drive = engineForce / 2;   // split across the driven axle
    for (let i = 0; i < 4; i++) {
      const isRear = i >= 2;
      // Keep driving the rears through a handbrake turn to sustain the slide.
      this.controller.setWheelEngineForce(i, isRear ? drive * (this.handbrake ? 1.35 : 1) : 0);
      let b = brakeForce;
      if (this.handbrake && isRear) b = handbrakeForce;
      this.controller.setWheelBrake(i, b);
      this.controller.setWheelFrictionSlip(i, isRear ? rearGrip : frontGrip);
    }

    this.controller.updateVehicle(
      dt, undefined, groups(GROUP.VEHICLE, GROUP.TERRAIN | GROUP.STATIC | GROUP.BUILDING | GROUP.PROP),
    );

    /* -------------------------------------------------------------- tyre slip */
    // Slip is taken from the solver's own lateral impulse rather than guessed from
    // steering angle: it therefore reflects what the tyres are actually doing, including
    // during a handbrake turn or when the car is shunted sideways.
    const lateral = this._vel.dot(this._right ?? this._forward);
    for (let i = 0; i < 4; i++) {
      const inContact = this.controller.wheelIsInContact(i);
      if (!inContact) {
        this.wheelSlip[i] = 0;
        this.wheelContacts[i] = null;
        continue;
      }
      const side = Math.abs(this.controller.wheelSideImpulse(i) ?? 0);
      const isRear = i >= 2;
      let slip = MathUtils.clamp(side / (this.spec.mass * 0.09), 0, 1);
      if (this.handbrake && isRear && absSpeed > 3) slip = Math.max(slip, 0.85);
      // Wheelspin under power from a standstill.
      if (this.throttle > 0.85 && isRear && absSpeed < 6) slip = Math.max(slip, 0.55);
      this.wheelSlip[i] = slip;

      const p = this.controller.wheelContactPoint(i);
      if (p) {
        this.wheelContacts[i] = this.wheelContacts[i] ?? new Vector3();
        this.wheelContacts[i].set(p.x, p.y, p.z);
      } else {
        this.wheelContacts[i] = null;
      }
    }
    void lateral;

    /*
     * Lane-keeping assist for AI traffic on constrained roads.
     *
     * Steering alone is not precise enough to hold a two-lane elevated deck: small errors
     * accumulate, the car drifts into a barrier and pins there. This is a gentle sideways
     * force towards the lane centre - a magnetic rail. It is invisible at the scale it
     * operates, it cannot fight the driver (only AI cars set it), and it makes elevated
     * traffic robust without demanding a perfect controller.
     *
     * Applied here rather than in the AI because `resetForces` at the top of this method
     * would otherwise wipe it.
     */
    if (this.laneAssist) {
      this.body.addForce({
        x: this.laneAssist.x, y: 0, z: this.laneAssist.z,
      }, true);
      this.laneAssist = null;
    }

    // Aerodynamic drag and a downforce term that plants the car at speed.
    if (absSpeed > 1) {
      const dragCoefficient = 0.42;
      const drag = -dragCoefficient * this.speed * absSpeed;
      this.body.addForce(
        { x: this._forward.x * drag, y: 0, z: this._forward.z * drag }, true,
      );
      this.body.addForce({ x: 0, y: -absSpeed * absSpeed * 0.9, z: 0 }, true);
    }
  }

  /**
   * Pick a detail tier from camera distance. With well over a hundred cars in the world,
   * lamps and wheel articulation on the far side of the map are pure draw-call cost for
   * something a couple of pixels wide.
   *
   * @param {number} distanceSq squared distance to the camera
   */
  setLodFromDistance(distanceSq) {
    const tier = distanceSq > 240 * 240 ? 2 : distanceSq > 110 * 110 ? 1 : 0;
    if (tier === this.lod) return;
    this.lod = tier;
    for (const d of this.detailParts) d.visible = tier < 1;
    for (const w of this.wheelObjects) w.visible = tier < 2;
  }

  /** Per-frame visual sync: wheels, lights, sirens. */
  render(dt) {
    const t = this.body.translation();
    const r = this.body.rotation();
    this.group.position.set(t.x, t.y, t.z);
    this.group.quaternion.set(r.x, r.y, r.z, r.w);

    if (this.lod >= 2) return;   // body-only: nothing left to animate

    for (let i = 0; i < 4; i++) {
      const w = this.wheelObjects[i];
      const connection = this.wheelPositions[i];
      const suspension = this.controller.wheelSuspensionLength(i) ?? 0.32;
      w.position.set(connection.x, connection.y - suspension, connection.z);
      w.rotation.y = this.controller.wheelSteering(i) ?? 0;
      w.rotation.x = this.controller.wheelRotation(i) ?? 0;
    }

    const lit = this.headlightsOn;
    for (const h of this.headlights) h.material.emissiveIntensity = lit ? 2.4 : 0.15;
    for (const t2 of this.taillights) {
      t2.material.emissiveIntensity = this.brake > 0.1 ? 2.6 : (lit ? 0.9 : 0.25);
    }

    if (this.lightbar) {
      this._sirenPhase += dt * 7;
      const flip = Math.sin(this._sirenPhase) > 0;
      this.lightbar.red.material.emissiveIntensity = flip ? 4 : 0.2;
      this.lightbar.blue.material.emissiveIntensity = flip ? 0.2 : 4;
    }
  }

  /** Seat position in world space, used to place the player on exit. */
  exitPoint(out = new Vector3()) {
    const r = this.body.rotation();
    this._quat.set(r.x, r.y, r.z, r.w);
    const side = out.set(-(this.spec.chassis.hx + 0.75), 0, 0).applyQuaternion(this._quat);
    const t = this.body.translation();
    return out.set(t.x + side.x, t.y + 0.2, t.z + side.z);
  }

  /** Camera follow point: slightly above and behind the roof line. */
  cameraFocus(out = new Vector3()) {
    const t = this.body.translation();
    return out.set(t.x, t.y + 0.2, t.z);
  }

  /**
   * Take damage. The paint material is cloned on first hit so a dented car does not
   * darken every other car that happens to share its colour - the material cache hands
   * out one instance per colour, which is exactly what we want until damage diverges.
   */
  applyDamage(amount) {
    if (amount <= 0) return false;
    this.health = Math.max(0, this.health - amount);
    this.damage = 1 - this.health / 100;

    if (!this._paintCloned && this.damage > 0.05) {
      const body = this.group.userData.shell?.children.find((c) => c.isMesh);
      if (body) {
        body.material = body.material.clone();
        body.material.userData.baseColor = body.material.color.clone();
        this._paint = body.material;
      }
      this._paintCloned = true;
    }
    if (this._paint) {
      const base = this._paint.userData.baseColor;
      this._paint.color.copy(base).multiplyScalar(1 - this.damage * 0.5);
      this._paint.roughness = 0.42 + this.damage * 0.45;
      this._paint.clearcoat = 0.55 * (1 - this.damage * 0.8);
    }

    if (this.health <= 0) this.engineOn = false;
    return this.health <= 0;
  }

  /** True once the car is wrecked enough to trail smoke. */
  get isSmoking() { return this.damage > 0.55; }

  /** Wake the body - Rapier sleeps idle rigid bodies and a sleeping car ignores input. */
  wake() { this.body.wakeUp(); }

  dispose() {
    this.physics.owners.delete(this.collider.handle);
    this.physics.world.removeVehicleController?.(this.controller);
    this.physics.world.removeRigidBody(this.body);
    this.group.removeFromParent();
  }
}

function yawQuat(yaw) {
  const h = yaw * 0.5;
  return { x: 0, y: Math.sin(h), z: 0, w: Math.cos(h) };
}

function yawQuatThree(yaw) {
  return new Quaternion(0, Math.sin(yaw * 0.5), 0, Math.cos(yaw * 0.5));
}
