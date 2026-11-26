# Parquet (WoodFloor051)

What I saw in 01_start, 12_level10, 19_level17: the floor's grain (detail_parquet_WoodFloor051,
albedo std 12/255, comparable to Wood's 15 and Tile's 10.8) already reads cleanly at play
distance, calm, not noisy, and the plank scale against the chairs/sideboards looked right.
But the normal map itself barely does anything: its R/G channel ranges are only +-4/+-10
around the midpoint, as flat as Metal's source (which the M7 pass already compensates to 2.0),
so at scale 1.0 the floor showed no catch-light relief at all, just scene shadows.

What I changed: `NormalScaleParquet` in Core/Tuning.cs (actually Assets/Scripts/Core/Tuning.cs),
from 1.0 to 1.4. Deliberately short of Metal's full 2.0 compensation since this floor fills most
of the frame and the Step22d noise probe caps how much noisier a textured view may read than the
flat one; a modest bump adds a faint sheen without matching Carpet/Upholstery's much larger
source variance even at their lower scales. `DetailTileParquet` left unchanged at 1.8, the plank
scale already looked correct relative to furniture.

What to check in the next shots: does the floor now show a faint sheen/highlight direction under
the sun light (good) or does any area start looking speckled/noisy, especially the large open
floors in 19_level17 (La maison) and 12_level10. If it still reads flat, 1.4 can go a bit higher;
if speckled, drop back toward 1.0-1.2.
