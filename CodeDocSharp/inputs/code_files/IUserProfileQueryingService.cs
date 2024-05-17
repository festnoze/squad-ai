using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileQueryingService
    {

    /// <summary>
    /// Retrieve payment reliability information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for a user which is an integer. This parameter is used to specify the user whose payment reliability information is to be retrieved.</param>
    /// <returns>Returns a user's payment reliability score asynchronously.</returns>

        Task<string> GetPaymentReliabilityAsync(int userId);

    /// <summary>
    /// Retrieve personal information for a specified user and ensure the data is not null, returning the information if available.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom personal information is being retrieved. This is an integer value.</param>
    /// <returns>Returns a user's personal information as a non-null object.</returns>

        Task<UserModel> GetUserWithPersonalInfosAsync(int userId);

    /// <summary>
    /// Retrieve basic information for a specified user.
    /// </summary>
    /// <param name="userId">The identifier of the user whose basic information is being retrieved.</param>
    /// <param name="schoolId">The identifier of the school associated with the user.</param>
    /// <param name="loadSchoolOptions">Specifies whether to load additional school options. Defaults to false.</param>
    /// <returns>Returns a user's basic information asynchronously.</returns>

        Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false);

    /// <summary>
    /// Retrieve basic public information for a specified user, then determine if the user has specific school options.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom to retrieve basic public information in the method 'GetUserWithPublicInfoAsync'.</param>
    /// <param name="schoolId">The identifier of the school to determine if the specified user has specific school options in the method 'GetUserWithPublicInfoAsync'.</param>
    /// <returns>Returns basic public user info and school options availability.</returns>

        Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve available school options for a specific user, given the user's ID and associated school ID.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. It is used to specify which user's school options are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school. It specifies the school context for the user whose options are being retrieved.</param>
    /// <returns>Returns user's available school options.</returns>

        Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId);

    /// <summary>
    /// Retrieve professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the professional experiences are to be retrieved.</param>
    /// <returns>Returns a list of the specified user's professional experiences.</returns>

        Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId);

    /// <summary>
    /// Retrieve the review date of a specified user's profile.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile review date is to be retrieved.</param>
    /// <returns>Returns the review date of a specified user's profile as an asynchronous task.</returns>

        Task<DateTime?> GetUserProfileReviewDateAsync(int userId);

    /// <summary>
    /// Retrieve the most recent study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose most recent study information is to be retrieved.</param>
    /// <returns>Returns the latest study details for a specified user.</returns>

        Task<StudyModel?> GetUserLastStudyInfosAsync(int userId);

    /// <summary>
    /// Retrieve a list of contract types relevant to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types for professional experiences.</returns>

        Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync();

    /// <summary>
    /// Retrieve the training records for a specific user associated with a particular school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose training records are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school with which the user is associated.</param>
    /// <returns>Returns a list of a user's training records for a specified school.</returns>
        Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve user notifications based on user ID and school ID.
    /// </summary>
    /// <param name="userId">The ID of the user for whom notifications are being retrieved.</param>
    /// <param name="schoolId">The ID of the school associated with the user's notifications.</param>
    /// <returns>Returns a list of user notifications.</returns>

        Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the time zone for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the time zone is to be retrieved.</param>
    /// <returns>Returns the user's time zone as a string.</returns>

        Task<string> GetUserTimeZoneAsync(int userId);

    /// <summary>
    /// Retrieve configuration information for a specific user and school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the configuration information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user for retrieving the configuration information.</param>
    /// <returns>Returns the configuration details for a specified user and school.</returns>

        Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the last session information for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose last session information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school where the user's last session information is to be retrieved.</param>
    /// <returns>Returns the user's last session details at the specified school.</returns>

        Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the first connection date is to be retrieved.</param>
    /// <returns>Returns the first connection date of the specified user as a DateTime.</returns>

        Task<DateTime?> GetUserFirstConnectionDateAsync(int userId);

    /// <summary>
    /// Get the avatar URL for a specified user; if the URL is invalid, return a default avatar URL.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose avatar URL is being requested.</param>
    /// <returns>Returns the user's avatar URL or a default URL if invalid.</returns>

        Task<string> GetAvatarUrlAsync(int userId);

    /// <summary>
    /// Check if a user exists by email.
    /// </summary>
    /// <param name="email">The email address to check for the user's existence.</param>
    /// <returns>Returns a task with a boolean indicating if the user exists by email.</returns>

        Task<bool> ExistUserByEmailAsync(string email);

    /// <summary>
    /// Check if a user exists by their pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudonym of the user. This parameter is used to identify and check if a user exists by their pseudonym in the 'ExistUserByPseudoAsync' method.</param>
    /// <returns>Returns a boolean indicating user's existence by pseudonym.</returns>

        Task<bool> ExistUserByPseudoAsync(string pseudo);

    /// <summary>
    /// Create a pseudo identifier for a user based on their first and last names.
    /// </summary>
    /// <param name="firstName">The user's given first name used to generate the pseudo identifier.</param>
    /// <param name="lastName">The user's surname used to generate the pseudo identifier.</param>
    /// <returns>Returns a pseudo identifier for the user.</returns>

        Task<string> GeneratePseudoAsync(string firstName, string lastName);

    /// <summary>
    /// Count the number of user profiles based on specified filter criteria.
    /// </summary>
    /// <param name="filtersCompositions">Optional. A collection of filters to apply to the user profiles. This parameter accepts an IEnumerable of IFiltersComposition of type object and is used to specify the filter criteria for counting the profiles. If not provided, no filters will be applied and the count will include all profiles.</param>
    /// <returns>Returns the count of user profiles matching the specified filters.</returns>

        Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null);

    /// <summary>
    /// Retrieve the user profiles with specified filters and sorting criteria, transform the filtering and sorting fields, and map civilities to the user profiles.
    /// </summary>
    /// <param name="skip">The number of records to skip, typically used for pagination purposes.</param>
    /// <param name="take">The number of records to take, indicating the size of the result set to return.</param>
    /// <param name="filtersCompositions">Optional parameter for a collection of filter compositions to apply various filters dynamically on the user profiles.</param>
    /// <param name="sort">Optional parameter to define the sorting criteria based on which the user profiles should be ordered.</param>
    /// <returns>Returns a list of user profiles based on applied filters and sorting criteria.</returns>

        Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null);

    /// <summary>
    /// Retrieve the user profile along with corresponding civility data if available.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile is to be retrieved.</param>
    /// <returns>Returns a task with the user's profile and optional civility data.</returns>

        Task<IUserProfileRAto> GetUserProfileAsync(int userId);
    }
}