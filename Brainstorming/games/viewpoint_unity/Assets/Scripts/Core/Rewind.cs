using System.Collections.Generic;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// One motion snapshot of the level: the player, the counters, the held
    /// photo and the pose of every tracked rigid body at a given instant.
    /// Angles are in RADIANS, like the pitch clamp of PRD section 8
    /// (+-1.45 rad) and like the mouse sensitivity (rad per pixel), so the
    /// seam the yaw lerp must cross the short way is +-pi.
    /// </summary>
    public sealed class RewindSample
    {
        public float T;
        public Vector3 PlayerPos;
        public float Yaw;
        public float Pitch;
        public int Carried;
        public int Sealed;
        public int Inserted;
        public int Required;
        public int Films;
        public string HeldId;
        public int Roll;

        /// Pose of every tracked body, keyed by GetInstanceID.
        public Dictionary<int, (Vector3 pos, Quaternion rot)> Bodies;

        /// The body table is shared, not copied: it is built once per sample
        /// and never mutated afterwards, so a blended copy can point at it.
        public RewindSample Clone()
        {
            RewindSample copy = new RewindSample();
            copy.T = T;
            copy.PlayerPos = PlayerPos;
            copy.Yaw = Yaw;
            copy.Pitch = Pitch;
            copy.Carried = Carried;
            copy.Sealed = Sealed;
            copy.Inserted = Inserted;
            copy.Required = Required;
            copy.Films = Films;
            copy.HeldId = HeldId;
            copy.Roll = Roll;
            copy.Bodies = Bodies;
            return copy;
        }
    }

    /// <summary>
    /// Time rewind, held on R. Two tracks, because a level changes in two very
    /// different ways:
    ///
    /// - MOTION, continuous: the player and the loose rigid bodies. Sampled at
    ///   a fixed rate into a ring of snapshots, replayed backwards with
    ///   interpolation.
    /// - STRUCTURE, discrete and rare: a photo placed, a wall carved, a cage
    ///   broken, a battery taken. Recorded as timestamped events.
    ///
    /// The structural side is exact rather than reconstructed: while a level is
    /// running NOTHING is really destroyed. A "destroyed" object is pulled out
    /// of the level hierarchy into a graveyard and deactivated, which takes it
    /// out of every registry (components unregister in OnDisable) and out of
    /// physics just like a destroy would, but keeps it whole. Undoing is
    /// putting it back. Objects only die for good when their event falls out of
    /// the history window.
    ///
    /// The counters (batteries, film) and the held photo ride along in the
    /// motion snapshots, so they rewind with everything else.
    /// </summary>
    public sealed class Rewind : MonoBehaviour
    {
        /// Motion snapshots per second. 20 Hz is invisible at rewind speed and
        /// cheap: a snapshot is the player plus a handful of rigid bodies.
        public const float SampleHz = 20f;

        /// History ceiling, about five minutes. Older samples (and the events
        /// they covered) are dropped, which is also when retired objects are
        /// truly destroyed.
        public const int MaxSamples = 6000;

        /// Seconds of history undone per second of holding R.
        public const float RewindSpeed = 2.5f;

        public static Rewind Instance { get; private set; }

        enum Kind
        {
            Spawn,
            Retire
        }

        /// A structural change, with everything needed to put the world back:
        /// the object, where it hung and the pose it had when it left.
        sealed class RewindEvent
        {
            public float T;
            public Kind EventKind;
            public GameObject Node;
            public Transform Parent;
            public int SiblingIndex;
            public Vector3 Pos;
            public Quaternion Rot;
            public Vector3 Scale;
        }

        PlayerController _player;
        Transform _levelRoot;
        Transform _graveyard;

        /// Motion track, oldest first.
        readonly List<RewindSample> _samples = new List<RewindSample>();

        /// Structural track, oldest first.
        readonly List<RewindEvent> _events = new List<RewindEvent>();

        /// Rigid bodies whose transform must be recorded (placed crates,
        /// placed battery shells).
        readonly List<Rigidbody> _tracked = new List<Rigidbody>();

        /// What each tracked body was before the rewind froze it, so stopping
        /// restores rather than assuming everything was dynamic.
        readonly Dictionary<int, bool> _wasKinematic = new Dictionary<int, bool>();

        float _time;
        float _sinceSample;
        bool _rewinding;

        /// Playback head while rewinding, in the same clock as _time.
        float _cursor;

        public bool IsRewinding => _rewinding;

        /// Size of each track, for the probe and for tuning.
        public int SampleCount => _samples.Count;

        public int EventCount => _events.Count;

        /// Kept for context: the level hierarchy this history belongs to.
        public Transform LevelRoot => _levelRoot;

        void Awake()
        {
            Instance = this;
            EnsureGraveyard();
        }

        void OnDestroy()
        {
            // A play mode without domain reload (or a test running twice) must
            // not leave a destroyed component behind as the instance.
            if (Instance == this)
            {
                Instance = null;
            }
            // The graveyard is a child of this object, so Unity takes it down
            // with us. The original had to free its own by hand because there it
            // was an orphan node kept outside the tree.
            _graveyard = null;
        }

        public void Setup(PlayerController player, Transform levelRoot)
        {
            _player = player;
            _levelRoot = levelRoot;
        }

        /// Called once the new level is built and GameState holds its counters:
        /// the history restarts from this state and nothing of the previous
        /// level survives.
        public void BeginLevel()
        {
            _rewinding = false;
            _samples.Clear();
            _events.Clear();
            _tracked.Clear();
            _wasKinematic.Clear();
            ClearGraveyard();
            _time = 0f;
            _sinceSample = 0f;
            _cursor = 0f;
            if (_player != null)
            {
                _samples.Add(Capture());
            }
        }

        /// How far back the history can still go, in seconds.
        public float AvailableSeconds()
        {
            if (_samples.Count == 0)
            {
                return 0f;
            }
            float head = _rewinding ? _cursor : _time;
            return Mathf.Max(0f, head - _samples[0].T);
        }

        // --- Recording -------------------------------------------------------

        /// Recording rides the physics clock, not the render clock: its delta is
        /// fixed, so the history means the same thing whatever the frame rate
        /// does.
        void FixedUpdate()
        {
            if (_rewinding || _player == null)
            {
                return;
            }
            float delta = Time.fixedDeltaTime;
            _time += delta;
            _sinceSample += delta;
            if (_sinceSample < 1f / SampleHz)
            {
                return;
            }
            _sinceSample = 0f;
            _samples.Add(Capture());
            Trim();
        }

        /// Registers a rigid body whose motion must be rewindable.
        public static void TrackBody(Rigidbody body)
        {
            if (body == null || Instance == null)
            {
                return;
            }
            if (!Instance._tracked.Contains(body))
            {
                Instance._tracked.Add(body);
            }
        }

        /// Records an object that just appeared. Undoing its creation retires
        /// it.
        public static void NoticeSpawn(GameObject node)
        {
            if (node == null || Instance == null || Instance._rewinding)
            {
                return;
            }
            Transform tr = node.transform;
            RewindEvent spawn = new RewindEvent();
            spawn.T = Instance._time;
            spawn.EventKind = Kind.Spawn;
            spawn.Node = node;
            spawn.Parent = tr.parent;
            spawn.SiblingIndex = tr.GetSiblingIndex();
            spawn.Pos = tr.position;
            spawn.Rot = tr.rotation;
            spawn.Scale = tr.localScale;
            Instance._events.Add(spawn);
        }

        /// Destroys an object the rewindable way: out of the level, into the
        /// graveyard, deactivated, so it leaves every registry and the physics
        /// world but stays whole. Falls back to a real destruction when no
        /// rewind is running (EditMode tests, tooling).
        public static void Retire(GameObject node)
        {
            if (node == null)
            {
                return;
            }
            if (Instance == null)
            {
                DestroyNow(node);
                return;
            }
            Instance.RetireInternal(node);
        }

        void RetireInternal(GameObject node)
        {
            EnsureGraveyard();
            Transform tr = node.transform;
            if (!_rewinding)
            {
                RewindEvent retire = new RewindEvent();
                retire.T = _time;
                retire.EventKind = Kind.Retire;
                retire.Node = node;
                retire.Parent = tr.parent;
                retire.SiblingIndex = tr.GetSiblingIndex();
                // A retired object keeps its place: putting it back must not
                // move it.
                retire.Pos = tr.position;
                retire.Rot = tr.rotation;
                retire.Scale = tr.localScale;
                _events.Add(retire);
            }
            tr.SetParent(_graveyard, true);
            node.SetActive(false);
        }

        RewindSample Capture()
        {
            RewindSample sample = new RewindSample();
            sample.T = _time;
            sample.PlayerPos = _player.transform.position;
            sample.Yaw = PlayerYaw();
            sample.Pitch = PlayerPitch();
            GameState state = GameState.Instance;
            sample.Carried = state.CarriedBatteries;
            sample.Sealed = state.CarriedSealed;
            sample.Inserted = state.InsertedBatteries;
            sample.Required = state.RequiredBatteries;
            sample.Films = state.CameraFilms;
            sample.HeldId = _player.Placer == null ? "" : _player.Placer.HeldId;
            sample.Roll = _player.Placer == null ? 0 : _player.Placer.RollSteps;

            Dictionary<int, (Vector3 pos, Quaternion rot)> bodies =
                new Dictionary<int, (Vector3 pos, Quaternion rot)>();
            for (int i = 0; i < _tracked.Count; i++)
            {
                Rigidbody body = _tracked[i];
                // An inactive body is a retired one: it is out of the world,
                // exactly like a body outside the Godot tree was.
                if (body == null || !body.gameObject.activeInHierarchy)
                {
                    continue;
                }
                Transform tr = body.transform;
                bodies[body.GetInstanceID()] = (tr.position, tr.rotation);
            }
            sample.Bodies = bodies;
            return sample;
        }

        /// Drops history beyond the ceiling. Events that fall out can never be
        /// undone again, so the objects they retired are destroyed for real
        /// here.
        void Trim()
        {
            if (_samples.Count <= MaxSamples)
            {
                return;
            }
            _samples.RemoveRange(0, _samples.Count - MaxSamples);
            float horizon = _samples[0].T;
            int kept = 0;
            for (int i = 0; i < _events.Count; i++)
            {
                RewindEvent entry = _events[i];
                if (entry.T >= horizon)
                {
                    _events[kept] = entry;
                    kept++;
                    continue;
                }
                bool retiredForGood = entry.EventKind == Kind.Retire
                    && entry.Node != null
                    && _graveyard != null
                    && entry.Node.transform.parent == _graveyard;
                if (retiredForGood)
                {
                    DestroyNow(entry.Node);
                }
            }
            _events.RemoveRange(kept, _events.Count - kept);
        }

        // --- Playback --------------------------------------------------------

        public void StartRewind()
        {
            if (_rewinding || _samples.Count == 0)
            {
                return;
            }
            _rewinding = true;
            _cursor = _time;
            _wasKinematic.Clear();
            for (int i = 0; i < _tracked.Count; i++)
            {
                Rigidbody body = _tracked[i];
                if (body == null)
                {
                    continue;
                }
                _wasKinematic[body.GetInstanceID()] = body.isKinematic;
                body.isKinematic = true;
            }
        }

        /// Walks the playback head back by delta seconds of holding.
        public void StepRewind(float delta)
        {
            if (!_rewinding || _samples.Count == 0)
            {
                return;
            }
            _cursor = Mathf.Max(_cursor - delta * RewindSpeed, _samples[0].T);
            UndoEventsAfter(_cursor);
            Apply(SampleAt(_samples, _cursor));
        }

        public void StopRewind()
        {
            if (!_rewinding)
            {
                return;
            }
            // The rewound future is gone: history restarts from the playback
            // head.
            int index = Locate(_samples, _cursor);
            if (index >= 0)
            {
                int tail = _samples.Count - index - 1;
                if (tail > 0)
                {
                    _samples.RemoveRange(index + 1, tail);
                }
                RewindSample head = CaptureAt(_cursor);
                if (head != null)
                {
                    _samples.Add(head);
                }
            }
            _time = _cursor;
            _sinceSample = 0f;
            _rewinding = false;
            for (int i = 0; i < _tracked.Count; i++)
            {
                Rigidbody body = _tracked[i];
                if (body == null)
                {
                    continue;
                }
                bool before;
                if (!_wasKinematic.TryGetValue(body.GetInstanceID(), out before))
                {
                    // Registered while the rewind was running: it was dynamic.
                    before = false;
                }
                body.isKinematic = before;
            }
            _wasKinematic.Clear();
        }

        void UndoEventsAfter(float t)
        {
            while (_events.Count > 0)
            {
                RewindEvent entry = _events[_events.Count - 1];
                if (entry.T <= t)
                {
                    return;
                }
                _events.RemoveAt(_events.Count - 1);
                if (entry.Node == null)
                {
                    continue;
                }
                if (entry.EventKind == Kind.Spawn)
                {
                    RetireInternal(entry.Node);
                }
                else
                {
                    Revive(entry);
                }
            }
        }

        void Revive(RewindEvent entry)
        {
            // The level the object belonged to is gone: it stays retired.
            if (entry.Parent == null)
            {
                return;
            }
            Transform tr = entry.Node.transform;
            tr.SetParent(entry.Parent, false);
            tr.SetPositionAndRotation(entry.Pos, entry.Rot);
            tr.localScale = entry.Scale;
            if (entry.SiblingIndex >= 0 && entry.SiblingIndex < entry.Parent.childCount)
            {
                tr.SetSiblingIndex(entry.SiblingIndex);
            }
            // Last, so the components that register in OnEnable wake up already
            // parented and already in place.
            entry.Node.SetActive(true);
        }

        void Apply(RewindSample state)
        {
            if (state == null || _player == null)
            {
                return;
            }
            _player.Teleport(state.PlayerPos);
            _player.SetLook(state.Yaw * Mathf.Rad2Deg, state.Pitch * Mathf.Rad2Deg);
            GameState.Instance.RestoreCounters(state.Carried, state.Inserted, state.Required,
                state.Films, state.Sealed);
            if (_player.Placer != null)
            {
                _player.Placer.RestoreHeld(state.HeldId, state.Roll);
            }
            if (state.Bodies == null)
            {
                return;
            }
            for (int i = 0; i < _tracked.Count; i++)
            {
                Rigidbody body = _tracked[i];
                if (body == null || !body.gameObject.activeInHierarchy)
                {
                    continue;
                }
                (Vector3 pos, Quaternion rot) pose;
                if (!state.Bodies.TryGetValue(body.GetInstanceID(), out pose))
                {
                    continue;
                }
                body.transform.SetPositionAndRotation(pose.pos, pose.rot);
                if (!body.isKinematic)
                {
                    body.linearVelocity = Vector3.zero;
                    body.angularVelocity = Vector3.zero;
                }
            }
        }

        /// Snapshot of the playback head, used to restart the history on
        /// release.
        RewindSample CaptureAt(float t)
        {
            RewindSample state = SampleAt(_samples, t);
            if (state == null)
            {
                return null;
            }
            RewindSample copy = state.Clone();
            copy.T = t;
            return copy;
        }

        // --- Pure helpers, unit tested ---------------------------------------

        /// Index of the last sample at or before t (0 when t precedes the
        /// history, -1 when there is none).
        public static int Locate(List<RewindSample> samples, float t)
        {
            if (samples == null || samples.Count == 0)
            {
                return -1;
            }
            int low = 0;
            int high = samples.Count - 1;
            while (low < high)
            {
                int mid = (low + high + 1) / 2;
                if (samples[mid].T <= t)
                {
                    low = mid;
                }
                else
                {
                    high = mid - 1;
                }
            }
            return low;
        }

        /// State at an arbitrary time: the bracketing samples blended for the
        /// smooth fields, the discrete ones taken from the earlier sample (a
        /// battery is picked up at one instant, it is never half picked up).
        public static RewindSample SampleAt(List<RewindSample> samples, float t)
        {
            int index = Locate(samples, t);
            if (index < 0)
            {
                return null;
            }
            RewindSample before = samples[index];
            if (index + 1 >= samples.Count)
            {
                return before;
            }
            RewindSample after = samples[index + 1];
            float span = after.T - before.T;
            float ratio = span <= 0f ? 0f : Mathf.Clamp01((t - before.T) / span);
            RewindSample blended = before.Clone();
            blended.T = t;
            blended.PlayerPos = Vector3.Lerp(before.PlayerPos, after.PlayerPos, ratio);
            blended.Yaw = LerpRadians(before.Yaw, after.Yaw, ratio);
            blended.Pitch = Mathf.Lerp(before.Pitch, after.Pitch, ratio);
            return blended;
        }

        /// Godot's lerp_angle, in radians: the shortest arc, so a rewind across
        /// the +-pi seam does not spin the player around.
        static float LerpRadians(float from, float to, float ratio)
        {
            float turn = Mathf.PI * 2f;
            float delta = Mathf.Repeat(to - from, turn);
            if (delta > Mathf.PI)
            {
                delta -= turn;
            }
            return from + delta * ratio;
        }

        // --- Internals -------------------------------------------------------

        float PlayerYaw()
        {
            return WrapPi(_player.transform.localEulerAngles.y * Mathf.Deg2Rad);
        }

        float PlayerPitch()
        {
            if (_player.Camera == null)
            {
                return 0f;
            }
            return WrapPi(_player.Camera.transform.localEulerAngles.x * Mathf.Deg2Rad);
        }

        /// Euler angles come back in [0, 360): folded to [-pi, pi] so that two
        /// consecutive samples never straddle the seam by a whole turn.
        static float WrapPi(float radians)
        {
            float turn = Mathf.PI * 2f;
            return Mathf.Repeat(radians + Mathf.PI, turn) - Mathf.PI;
        }

        void EnsureGraveyard()
        {
            if (_graveyard != null)
            {
                return;
            }
            // Deliberately INACTIVE: an inactive holder keeps its children alive
            // but out of every registry and out of physics, which is what takes
            // a retired object out of the world exactly like a destroy would.
            GameObject holder = new GameObject("RewindGraveyard");
            holder.transform.SetParent(transform, false);
            holder.SetActive(false);
            _graveyard = holder.transform;
        }

        void ClearGraveyard()
        {
            EnsureGraveyard();
            for (int i = _graveyard.childCount - 1; i >= 0; i--)
            {
                DestroyNow(_graveyard.GetChild(i).gameObject);
            }
        }

        /// Destroy, whichever way the current context allows: EditMode tests and
        /// tooling run outside play mode, where Destroy never happens.
        static void DestroyNow(GameObject node)
        {
            if (node == null)
            {
                return;
            }
            if (Application.isPlaying)
            {
                UnityEngine.Object.Destroy(node);
                return;
            }
            UnityEngine.Object.DestroyImmediate(node);
        }
    }
}
