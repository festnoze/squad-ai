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
    /// Verify the validity of a user ID being positive and non-zero, then retrieve the payment reliability information for the specified user ID.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile and civility details are to be retrieved and formatted.</param>
    /// <returns>Returns the user's payment reliability status.</returns>

        Task<string> GetPaymentReliabilityAsync(int userId);

    /// <summary>
    /// Retrieve personal information for a specified user. Ensure that the user's information exists and handle cases where it is not found.
    /// </summary>
    /// <param name="userId">Specifies the user ID for which the user's profile information and civility details need to be retrieved and mapped.</param>
    /// <returns>Returns the user's profile and civility information.</returns>

        Task<UserModel> GetUserWithPersonalInfosAsync(int userId);

    /// <summary>
    /// Retrieve basic information for a specified user, with error handling for non-existent users.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user, necessary for mapping the data to a specific format.</param>
    /// <param name="loadSchoolOptions">A boolean flag indicating whether school options should be loaded during the retrieval process.</param>
    /// <returns>Returns basic user information or an error if user does not exist.</returns>

        Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false);

    /// <summary>
    /// Retrieve user information along with public details, considering validation and checks for null values and corresponding school options for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user, used to fetch relevant information within the specified context.</param>
    /// <returns>Returns user info with public details for the specified user and school.</returns>

        Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve available school options for a specified user within a specific school, ensuring the retrieved data is not null, and constructing a model with the retrieved information.
    /// </summary>
    /// <param name="userId">The unique identifier representing the user whose profile information and civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user, necessary to map the data into the specified format.</param>
    /// <returns>Returns available school options for the specified user in a specified school.</returns>

        Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId);

    /// <summary>
    /// Retrieve professional experiences associated with a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. It is used to retrieve the user's profile information and civility details in the GetUserProfessionalExperiencesAsync method.</param>
    /// <returns>Returns the user's professional experiences asynchronously.</returns>

        Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId);

    /// <summary>
    /// Retrieve the review date of a user's profile using the user's unique identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns the review date of a user's profile as a DateTime object.</returns>

        Task<DateTime?> GetUserProfileReviewDateAsync(int userId);

    /// <summary>
    /// Retrieve the most recent study information for a specific user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile information and civility details are being retrieved.</param>
    /// <returns>Returns the user's most recent study information asynchronously.</returns>

        Task<StudyModel?> GetUserLastStudyInfosAsync(int userId);

    /// <summary>
    /// Retrieve the list of contract types related to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types associated with professional experiences.</returns>

        Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync();

    /// <summary>
    /// Retrieve training records for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user's profile information.</param>
    /// <returns>Returns a list of training records for the specified user and school.</returns>
        Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve user notification settings for a specified user and school combination.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to associate the user's information with.</param>
    /// <returns>Returns user notification settings.</returns>

        Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Get the time zone for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <returns>Returns the user's time zone in asynchronous operation.</returns>

        Task<string> GetUserTimeZoneAsync(int userId);

    /// <summary>
    /// Retrieve configuration information for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user belongs.</param>
    /// <returns>Returns a task with user configuration information for the specified school.</returns>

        Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the last session information for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns the last session information for a given user and school asynchronously.</returns>

        Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the first connection date of a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved and mapped.</param>
    /// <returns>Returns the first connection date of the specified user as a Task<DateTime>.</returns>

        Task<DateTime?> GetUserFirstConnectionDateAsync(int userId);

    /// <summary>
    /// Retrieve the avatar URL for a specified user, if available, or return a default avatar URL.
    /// </summary>
    /// <param name="userId">The identifier for the user whose profile information and civility details need to be retrieved. It is an integer value that specifies the user ID.</param>
    /// <returns>Returns the user's avatar URL or a default URL if not available.</returns>

        Task<string> GetAvatarUrlAsync(int userId);

    /// <summary>
    /// Check whether a user exists based on their email.
    /// </summary>
    /// <param name="email">The email address of the user whose profile information and civility details need to be retrieved.</param>
    /// <returns>Returns a boolean indicating if a user exists for the given email.</returns>

        Task<bool> ExistUserByEmailAsync(string email);

    /// <summary>
    /// Check for the existence of a user by their pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudonym of the user whose profile information and civility details are to be retrieved. This parameter is crucial for identifying the specific user.</param>
    /// <returns>Returns a task indicating whether the user exists.</returns>

        Task<bool> ExistUserByPseudoAsync(string pseudo);

    /// <summary>
    /// Generate a pseudo name for a user based on their first and last names.
    /// </summary>
    /// <param name="firstName">The first name of the user whose profile information is being retrieved.</param>
    /// <param name="lastName">The last name of the user whose profile information is being retrieved.</param>
    /// <returns>Returns a pseudo name based on the user's first and last names.</returns>

        Task<string> GeneratePseudoAsync(string firstName, string lastName);

    /// <summary>
    /// Count the number of user profiles based on specified filters.
    /// </summary>
    /// <param name="filtersCompositions">An optional collection of filter compositions that may be used to refine which user profiles are retrieved. This encompasses a set of defined filter rules, and if left null, the default fetching without any filters will be applied.</param>
    /// <returns>Returns the total count of user profiles matching the filters.</returns>

        Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null);

    /// <summary>
    /// Retrieve user profiles based on specified filters and sort criteria, and map them to a specific format, including associated civility IDs if available.
    /// </summary>
    /// <param name="skip">The number of items to be skipped before starting to collect the result set. This is useful for pagination.</param>
    /// <param name="take">The number of items to be included in the result set. This is useful for pagination.</param>
    /// <param name="filtersCompositions">A collection of filter compositions applied to the data. This allows the filtering of results based on specific conditions. It can be null.</param>
    /// <param name="sort">An object that specifies the sort order of the results. This allows sorting based on certain criteria. It can be null.</param>
    /// <returns>Returns a list of mapped user profiles with optional civility IDs.</returns>

        Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null);

    /// <summary>
    /// Retrieve a user's profile information and civility details based on a specified user ID, and map this data into a specific format.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns the user's formatted profile and civility details.</returns>

        Task<IUserProfileRAto> GetUserProfileAsync(int userId);
    }
}