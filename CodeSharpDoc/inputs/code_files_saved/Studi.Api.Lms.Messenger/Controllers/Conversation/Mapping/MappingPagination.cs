using Studi.Api.Core.ListingSelector.Filtering.FilterCompositions.Implementation;
using Studi.Api.Core.ListingSelector.Filtering.FilterCompositions;
using Studi.Api.Core.ListingSelector.Filtering.FilterCriteria.Implementation;
using Studi.Api.Core.ListingSelector.Filtering.AvailableFilters;
using Studi.Api.Core.ListingSelector.Untyped;
using Studi.Api.Lms.Messenger.Shared.ConversationListing;

namespace Studi.Api.Lms.Messenger.Controllers.Conversation.Mapping;

internal static class MappingPagination
{
    public static IEnumerable<IFilterComposition<IConversationListing>> GetValidatedFiltersForConversation(IEnumerable<IUntypedFiltersComposition> filtersCompositions, IAvailableFilters<IConversationListing> availableFiltersForConversation)
    {
        var result = new List<IFilterComposition<IConversationListing>>();
        foreach (var filtersComposition in filtersCompositions)
        {
            var newTypedFilterComposition = new FilterComposition<IConversationListing>(filtersComposition.Logic);
            foreach (var filter in filtersComposition.Filters)
            {
                var newTypedFilter = FilterCriteria<IConversationListing>.CreateAndVerifyWithTypedValue(
                                                                                filter.FilterName, 
                                                                                filter.Operator?.ToString(), 
                                                                                filter.Value, 
                                                                                availableFiltersForConversation);
                newTypedFilterComposition.AddFilter(newTypedFilter);
            }
            result.Add(newTypedFilterComposition);
        }
        return result;
    }
}
