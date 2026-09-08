using System.Collections.Generic;

namespace Billing.Api.Services
{
    public class InvoiceService
    {
        public List<int> ListAll()
        {
            return new List<int>();
        }

        public object Retry(int id)
        {
            return new { invoice = id, windowDays = 3 };
        }
    }
}
