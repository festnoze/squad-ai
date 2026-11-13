using UnityEngine;
using UnityEngine.InputSystem;

namespace Smoke
{
    /// <summary>Moves the player cube on the XZ plane from the keyboard, or toward the nearest coin in autopilot.</summary>
    [RequireComponent(typeof(Rigidbody))]
    public sealed class PlayerController : MonoBehaviour
    {
        [SerializeField] private float speed = 6f;

        /// <summary>When true, the player steers itself toward the nearest remaining coin (smoke tests).</summary>
        public bool Autopilot { get; set; }

        private Rigidbody body;

        private void Awake()
        {
            body = GetComponent<Rigidbody>();
        }

        private void FixedUpdate()
        {
            Vector3 direction = Autopilot ? AutopilotDirection() : KeyboardDirection();
            Vector3 velocity = direction * speed;
            velocity.y = body.linearVelocity.y;
            body.linearVelocity = velocity;
        }

        private static Vector3 KeyboardDirection()
        {
            Keyboard keyboard = Keyboard.current;
            if (keyboard == null)
            {
                return Vector3.zero;
            }
            float x = 0f;
            float z = 0f;
            // Physical key positions: W/A map to Z/Q on an AZERTY keyboard.
            if (keyboard.wKey.isPressed || keyboard.upArrowKey.isPressed) z += 1f;
            if (keyboard.sKey.isPressed || keyboard.downArrowKey.isPressed) z -= 1f;
            if (keyboard.dKey.isPressed || keyboard.rightArrowKey.isPressed) x += 1f;
            if (keyboard.aKey.isPressed || keyboard.leftArrowKey.isPressed) x -= 1f;
            return Vector3.ClampMagnitude(new Vector3(x, 0f, z), 1f);
        }

        private Vector3 AutopilotDirection()
        {
            Coin nearest = null;
            float best = float.MaxValue;
            foreach (Coin coin in FindObjectsByType<Coin>(FindObjectsSortMode.None))
            {
                float d = (coin.transform.position - transform.position).sqrMagnitude;
                if (d < best)
                {
                    best = d;
                    nearest = coin;
                }
            }
            if (nearest == null)
            {
                return Vector3.zero;
            }
            Vector3 delta = nearest.transform.position - transform.position;
            delta.y = 0f;
            return delta.sqrMagnitude < 0.0001f ? Vector3.zero : delta.normalized;
        }
    }
}
