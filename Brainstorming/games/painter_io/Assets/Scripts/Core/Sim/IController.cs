// Written by A1 as the complete interface (contract 5.5), owned by A4.
namespace PainterIO.Core
{
    public interface IController
    {
        // Called once per tick, before motion, for alive players only. Return the desired heading (radians) or null to
        // keep it. Controllers must never mutate anything reachable from SimView.
        double? DesiredHeading(SimView view, int playerIndex);
    }
}
