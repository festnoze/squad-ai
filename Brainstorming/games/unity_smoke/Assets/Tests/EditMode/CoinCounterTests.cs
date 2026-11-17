using NUnit.Framework;
using Smoke;

namespace Smoke.Tests.EditMode
{
    public sealed class CoinCounterTests
    {
        [Test]
        public void Collecting_every_coin_completes_the_level()
        {
            var counter = new CoinCounter(3);
            Assert.IsFalse(counter.IsComplete);
            Assert.IsTrue(counter.Collect());
            Assert.IsTrue(counter.Collect());
            Assert.IsFalse(counter.IsComplete);
            Assert.IsTrue(counter.Collect());
            Assert.IsTrue(counter.IsComplete);
            Assert.AreEqual("Pieces : 3/3", counter.Label);
        }

        [Test]
        public void Collect_never_exceeds_total()
        {
            var counter = new CoinCounter(1);
            counter.Collect();
            Assert.IsFalse(counter.Collect());
            Assert.AreEqual(1, counter.Collected);
        }

        [Test]
        public void Empty_level_is_never_complete()
        {
            // A scene with zero coins must not report a win (guards against a test passing on an empty scene).
            var counter = new CoinCounter(0);
            Assert.IsFalse(counter.IsComplete);
            Assert.IsFalse(counter.Collect());
        }
    }
}
