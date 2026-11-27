// Owned by A3 (trail). Contract 5.4 and section 8.
using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    public static class LassoGeometry
    {
        /// <summary>
        /// R16 pocket validity: GridRaster.CountInterior(g, loop) * g.CellSize^2 &gt;= minArea. CountInterior uses the
        /// non-zero winding rule on cell centers, so the lobes of a figure-8 loop (opposite orientations) add up instead
        /// of cancelling, and the test agrees with the pocket raster (GridRaster.RasterPolygon). A loop with fewer than
        /// 3 points has no interior.
        /// </summary>
        public static bool IsValidPocket(OwnerGrid g, IReadOnlyList<Vec2d> loop, double minArea)
        {
            if (g == null) throw new ArgumentNullException(nameof(g));
            int interior = (loop == null || loop.Count < 3) ? 0 : GridRaster.CountInterior(g, loop);
            double cell = g.CellSize;
            return interior * cell * cell >= minArea;
        }
    }
}
