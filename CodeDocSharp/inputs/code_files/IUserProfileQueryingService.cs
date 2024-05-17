using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileQueryingService
    {

    None
        Task<string> GetPaymentReliabilityAsync(int userId);

    None
        Task<UserModel> GetUserWithPersonalInfosAsync(int userId);

    None
        Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false);

    None
        Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId);

    None
        Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId);

    None
        Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId);

    None
        Task<DateTime?> GetUserProfileReviewDateAsync(int userId);

    None
        Task<StudyModel?> GetUserLastStudyInfosAsync(int userId);

    None
        Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync();

    None        Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId);

    None
        Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId);

    None
        Task<string> GetUserTimeZoneAsync(int userId);

    None
        Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId);

    None
        Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId);

    None
        Task<DateTime?> GetUserFirstConnectionDateAsync(int userId);

    None
        Task<string> GetAvatarUrlAsync(int userId);

    None
        Task<bool> ExistUserByEmailAsync(string email);

    None
        Task<bool> ExistUserByPseudoAsync(string pseudo);

    None
        Task<string> GeneratePseudoAsync(string firstName, string lastName);

    None
        Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null);

    None
        Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null);

    None
        Task<IUserProfileRAto> GetUserProfileAsync(int userId);
    }
}