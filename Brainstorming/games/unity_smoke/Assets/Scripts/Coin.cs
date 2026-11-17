using UnityEngine;

namespace Smoke
{
    /// <summary>Spinning pickup. The trigger sits on this object, the visual is a child.</summary>
    [RequireComponent(typeof(SphereCollider))]
    public sealed class Coin : MonoBehaviour
    {
        [SerializeField] private float spinDegreesPerSecond = 120f;

        private void Update()
        {
            transform.Rotate(0f, spinDegreesPerSecond * Time.deltaTime, 0f, Space.World);
        }

        private void OnTriggerEnter(Collider other)
        {
            if (other.GetComponentInParent<PlayerController>() != null && GameManager.Instance != null)
            {
                GameManager.Instance.Collect(this);
            }
        }
    }
}
