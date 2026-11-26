# LV4 progress (levels 7 and 18) - TASK DONE

## level7 - DONE
- File = exact +90 rotation of HEAD (scratchpad lv4_check.py), dwells 2.0, sage/marble, rev 1,
  pace {0.35, 0.55, 2, 6.0}. Deviation by design: decoys 1 and 3 yaw 270 (face their desks) instead of 90.
- decoy_cells.py: 4 decoys, 1 ok cell each.
- Routes written in Build/LV4_write.log; replay confirmed in Build/LV4_confirm.log (no "differe" note).
- Numbers (both difficulties): 0 defects, exit 19.3, travel 9.6, wait 50 %, 2 pauses, longest 5.4 (spawn wait 5.4),
  slack 8, 24 explained samples (25 difficile), 6 glide stops ((96 - 24 x 3) / 4), glide binds, 52 dc / 18 mat.
- Warning (not a defect): delayed starts at 10-13 s of the 17.3 s loop have no schedule without an 8 s wait.

## level18 - DONE
- File = exact mirror of HEAD with hold 4.8. Deviations: porte_cuisine hinge kept 'start' (door in a vertical wall,
  hinge runs along z, unchanged by the x mirror; DoorGeometry.cs line 91); Odile station 0 dwell 0.5 -> 0.0
  (with 0.5: longest pause 6.1 > 6.0). Hold 4.7 fallback not used (slack 6, not > 7).
- Routes written Build/LV4_write3.log; replay confirmed Build/LV4_confirm.log.
- Numbers (both difficulties): 0 defects, exit 21.7, travel 11.5, wait 47 %, 2 pauses, longest 5.6 (spawn),
  hide pause 13.6-18.2 (4.6 s), wardrobe binds, slack 6, margin 0.3, 61 dc / 16 mat.
- Spec target "spawn or doorway wait <= 5 s" NOT met (5.6 s); not in the task acceptance list.

## Next step
None. Unity runs used this attempt: 2 (write3, confirm).
