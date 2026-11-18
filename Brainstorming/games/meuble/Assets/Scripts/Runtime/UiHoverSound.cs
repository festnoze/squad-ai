using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

namespace OutOfSight
{
    /// <summary>
    /// Audio overhaul (docs/audio/AUDIO_REPORT.md 2): the menu's selection tick (<see cref="Sfx.PlayUiHover"/>) on every menu
    /// button (added by <see cref="Hud.MenuButton"/>): when the mouse enters an interactable button, and when the arrows or
    /// the D-pad move the selection onto it. Never for a touch (the press already clicks), a click's own selection, or a
    /// selection made by code (a page opening on its default button): those come with a non-axis event.
    /// </summary>
    public sealed class UiHoverSound : MonoBehaviour, IPointerEnterHandler, ISelectHandler
    {
        public void OnPointerEnter(PointerEventData eventData)
        {
            if (eventData is ExtendedPointerEventData extended && extended.pointerType == UIPointerType.Touch)
            {
                return;
            }
            Tick();
        }

        public void OnSelect(BaseEventData eventData)
        {
            // Navigation (keyboard arrows, D-pad, stick) selects with an AxisEventData; a click with a PointerEventData and
            // EventSystem.SetSelectedGameObject from code with a plain BaseEventData.
            if (eventData is AxisEventData)
            {
                Tick();
            }
        }

        private void Tick()
        {
            if (TryGetComponent(out Selectable selectable) && !selectable.IsInteractable())
            {
                return;
            }
            Main main = Main.Instance;
            if (main != null && main.Sfx != null)
            {
                main.Sfx.PlayUiHover();
            }
        }
    }
}
