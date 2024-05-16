namespace Studi.Api.Lms.Application.Services;

using MediatR;
using Studi.Api.Core.Exceptions.ErrorCodesLocalization.Base;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.User.Application.Interfaces;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;
using Studi.Api.Lms.User.Domain.Aggregates.User.Queries;
using Studi.Api.Lms.User.Localization.Error.GeneratedClasses;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Application.Services.CustomWebResource;
using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Lms.User.Application.Decorators;
using Studi.Api.Lms.User.Application.Tools;
using Studi.Api.Lms.User.Application.Mapper;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Application.Services.Civility;
using Studi.Api.Lms.User.Common.RepositoriesInterfaces;

[ScopedService(typeof(IUserProfileQueryingService))]
public class UserProfileQueryingService : IUserProfileQueryingService
{
    private readonly IMediator _mediator;
    private readonly ICustomWebResourceService _customWebResource;
    private readonly ICivilityService _civilityService;
    private readonly IUserRepository _userRepository;


    /// <summary>
    /// Initialize the querying service with mediator, custom web resource, civility service, and user repository parameters, ensuring none are null.
    /// </summary>
    /// <param name="mediator">An instance of IMediator to coordinate and delegate calls between different parts of the system for the UserProfileQueryingService.</param>
    /// <param name="customWebResource">An instance of ICustomWebResourceService responsible for handling web resources used in retrieving and formatting user profile data.</param>
    /// <param name="civilityService">An instance of ICivilityService responsible for retrieving and managing civility-related information for user profiles.</param>
    /// <param name="userRepository">An instance of IUserRepository responsible for accessing and managing user data stored in the system's repositories.</param>
    public UserProfileQueryingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserRepository userRepository)
    {
        _mediator = mediator ?? throw new ArgumentNullException();
        _customWebResource = customWebResource ?? throw new ArgumentNullException();
        _civilityService = civilityService ?? throw new ArgumentNullException();
        _userRepository = userRepository;
    }


    /// <summary>
    /// Verify the validity of a user ID being positive and non-zero, then retrieve the payment reliability information for the specified user ID.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile and civility details are to be retrieved and formatted.</param>
    /// <returns>Returns the user's payment reliability status.</returns>
    public async Task<string?> GetPaymentReliabilityAsync(int userId)
    {
        Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Common.UserId.NegativeOrZero);
        return await _userRepository.GetPaymentReliabilityAsync(userId);
    }



    /// <summary>
    /// Retrieve basic information for a specified user, with error handling for non-existent users.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user, necessary for mapping the data to a specific format.</param>
    /// <param name="loadSchoolOptions">A boolean flag indicating whether school options should be loaded during the retrieval process.</param>
    /// <returns>Returns basic user information or an error if user does not exist.</returns>
    public async Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false)
    {
        var user = await _mediator.Send(new UserBaseQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.User.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        var userBasicInfoIto = await _mediator.Send(new UserBasicInfoQuery(userId));
        user!.SetBasicInfoInformations(BasicInfoModel.CreateExisting(userBasicInfoIto!));

        if (loadSchoolOptions)
        {
            var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
            Guard.Against.Null(userSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve user information along with public details, considering validation and checks for null values and corresponding school options for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user, used to fetch relevant information within the specified context.</param>
    /// <returns>Returns user info with public details for the specified user and school.</returns>
    public async Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId)
    {
        var user = await _mediator.Send(new UserPublicInfoQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.PublicInfo.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString()); //TODO Localize

        var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        if (userSchoolOptions != null)
        {
            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));

            var userScoresItos = await _mediator.Send(new UserScoresQuery(userId, schoolId));
            user!.SetUserScoresModel(userScoresItos is null ? null : UserScoresModel.CreateExisting(userScoresItos!));

            var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
            Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);
            user!.SetTrainings(TrainingModel.CreateExistingList(userTrainingsItos!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve the user along with their course registrations for a specified user ID and school ID.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile information and civility details will be retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school to which the user is associated. This helps in mapping the user's data within the context of the school.</param>
    /// <returns>Returns user and their course registrations for given user ID and school ID.</returns>
    //[Obsolete("replaced by Trainings")]
    //public async Task<UserModel> GetUserWithCoursesRegistrationsAsync(int userId, int schoolId)
    //{
    //    var user = await _mediator.Send(new UserCoursesRegistrationsQuery(userId, schoolId));
    //    return user.UserCoursesRegistrations.First().ToIto();
    //}


    /// <summary>
    /// Retrieve personal information for a specified user. Ensure that the user's information exists and handle cases where it is not found.
    /// </summary>
    /// <param name="userId">Specifies the user ID for which the user's profile information and civility details need to be retrieved and mapped.</param>
    /// <returns>Returns the user's profile and civility information.</returns>
    public async Task<UserModel> GetUserWithPersonalInfosAsync(int userId)
    {
        var userWPersonalInfos = await _mediator.Send(new UserPersonnalInformationsQuery(userId));
        Guard.Against.Null(userWPersonalInfos, ErrorCode.Api.Lms.User.DataValidation.Query.PersonnalInfos.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        return userWPersonalInfos!;
    }


    /// <summary>
    /// Retrieve available school options for a specified user within a specific school, ensuring the retrieved data is not null, and constructing a model with the retrieved information.
    /// </summary>
    /// <param name="userId">The unique identifier representing the user whose profile information and civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user, necessary to map the data into the specified format.</param>
    /// <returns>Returns available school options for the specified user in a specified school.</returns>
    public async Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId)
    {
        var userWSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        Guard.Against.Null(userWSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

        return UserSchoolOptionsModel.CreateExisting(userWSchoolOptions!);
    }


    /// <summary>
    /// Retrieve professional experiences associated with a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. It is used to retrieve the user's profile information and civility details in the GetUserProfessionalExperiencesAsync method.</param>
    /// <returns>Returns the user's professional experiences asynchronously.</returns>
    public async Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId)
    {
        return (await _mediator.Send(new UserProfessionalExperiencesQuery(userId))).ProfessionalExperiences;
    }


    /// <summary>
    /// Retrieve the review date of a user's profile using the user's unique identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns the review date of a user's profile as a DateTime object.</returns>
    public async Task<DateTime?> GetUserProfileReviewDateAsync(int userId)
    {
        return await _mediator.Send(new UserProfileReviewDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the most recent study information for a specific user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile information and civility details are being retrieved.</param>
    /// <returns>Returns the user's most recent study information asynchronously.</returns>
    public async Task<StudyModel?> GetUserLastStudyInfosAsync(int userId)
    {
        return await _mediator.Send(new UserLastStudyInfosQuery(userId));
    }


    /// <summary>
    /// Retrieve the list of contract types related to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types associated with professional experiences.</returns>
    public async Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync()
    {
        return await _mediator.Send(new AllContractTypesForProfessionalExperiencesQuery());
    }


    /// <summary>
    /// Retrieve training records for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user's profile information.</param>
    /// <returns>Returns a list of training records for the specified user and school.</returns>
    public async Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId)
    {
        var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
        Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);

        return TrainingModel.CreateExistingList(userTrainingsItos);
    }


    /// <summary>
    /// Retrieve user notification settings for a specified user and school combination.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to associate the user's information with.</param>
    /// <returns>Returns user notification settings.</returns>
    public async Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserNotificationsSettingsQuery(userId, schoolId));
    }


    /// <summary>
    /// Get the time zone for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <returns>Returns the user's time zone in asynchronous operation.</returns>
    public async Task<string> GetUserTimeZoneAsync(int userId)
    {
        return await _mediator.Send(new UserTimeZoneQuery(userId));
    }


    /// <summary>
    /// Retrieve configuration information for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user belongs.</param>
    /// <returns>Returns a task with user configuration information for the specified school.</returns>
    public async Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserConfigInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the last session information for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns the last session information for a given user and school asynchronously.</returns>
    public async Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserLastSessionInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the first connection date of a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved and mapped.</param>
    /// <returns>Returns the first connection date of the specified user as a Task<DateTime>.</returns>
    public async Task<DateTime?> GetUserFirstConnectionDateAsync(int userId)
    {
        return await _mediator.Send(new UserFirstConnectionDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the avatar URL for a specified user, if available, or return a default avatar URL.
    /// </summary>
    /// <param name="userId">The identifier for the user whose profile information and civility details need to be retrieved. It is an integer value that specifies the user ID.</param>
    /// <returns>Returns the user's avatar URL or a default URL if not available.</returns>
    public async Task<string> GetAvatarUrlAsync(int userId)
    {
        var url = await _mediator.Send(new UserAvatarUrlQuery(userId));

        if (!string.IsNullOrEmpty(url) 
            && !string.IsNullOrWhiteSpace(url))
            return url;

        return _customWebResource.DefaultAvatarUrl;
    }


    /// <summary>
    /// Check whether a user exists based on their email.
    /// </summary>
    /// <param name="email">The email address of the user whose profile information and civility details need to be retrieved.</param>
    /// <returns>Returns a boolean indicating if a user exists for the given email.</returns>
    public async Task<bool> ExistUserByEmailAsync(string email)
    {
        return await _mediator.Send(new UserExistByEmailQuery(email));
    }


    /// <summary>
    /// Check for the existence of a user by their pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudonym of the user whose profile information and civility details are to be retrieved. This parameter is crucial for identifying the specific user.</param>
    /// <returns>Returns a task indicating whether the user exists.</returns>
    public async Task<bool> ExistUserByPseudoAsync(string pseudo)
    {
        return await _mediator.Send(new UserExistByPseudoQuery(pseudo));
    }


    /// <summary>
    /// Generate a pseudo name for a user based on their first and last names.
    /// </summary>
    /// <param name="firstName">The first name of the user whose profile information is being retrieved.</param>
    /// <param name="lastName">The last name of the user whose profile information is being retrieved.</param>
    /// <returns>Returns a pseudo name based on the user's first and last names.</returns>
    public async Task<string> GeneratePseudoAsync(string firstName, string lastName)
    {
        return await _mediator.Send(new UserGeneratePseudoQuery(firstName, lastName));
    }


    /// <summary>
    /// Count the number of user profiles based on specified filters.
    /// </summary>
    /// <param name="filtersCompositions">An optional collection of filter compositions that may be used to refine which user profiles are retrieved. This encompasses a set of defined filter rules, and if left null, the default fetching without any filters will be applied.</param>
    /// <returns>Returns the total count of user profiles matching the filters.</returns>
    public async Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);

        return await _mediator.Send(new UserProfilesCountQuery(filtersCompositions));
    }


    /// <summary>
    /// Retrieve user profiles based on specified filters and sort criteria, and map them to a specific format, including associated civility IDs if available.
    /// </summary>
    /// <param name="skip">The number of items to be skipped before starting to collect the result set. This is useful for pagination.</param>
    /// <param name="take">The number of items to be included in the result set. This is useful for pagination.</param>
    /// <param name="filtersCompositions">A collection of filter compositions applied to the data. This allows the filtering of results based on specific conditions. It can be null.</param>
    /// <param name="sort">An object that specifies the sort order of the results. This allows sorting based on certain criteria. It can be null.</param>
    /// <returns>Returns a list of mapped user profiles with optional civility IDs.</returns>
    public async Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);
        PaginationTools.TransformSortFieldName(sort, fieldNameDecorator);

        var data = await _mediator.Send(new UserProfilesQuery(skip, take, filtersCompositions, sort));

        if(!data.Any())
            return Enumerable.Empty<IUserProfileRAto>();

        var civilities = this._civilityService.GetCivilities();
        return data.Select(q => ItoToAtoMapper.ToUserProfileRAto(q, civilities.FirstOrDefault(c => c.Name == q.Civility)?.Id));
    }


    /// <summary>
    /// Retrieve a user's profile information and civility details based on a specified user ID, and map this data into a specific format.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns the user's formatted profile and civility details.</returns>
    public async Task<IUserProfileRAto> GetUserProfileAsync(int userId)
    {
        var data = await _mediator.Send(new UserProfileQuery(userId));
        var civility = !string.IsNullOrEmpty(data.Civility) ? this._civilityService.GetCivilityByName(data.Civility!) : null;

        return ItoToAtoMapper.ToUserProfileRAto(data, civility?.Id);
    }
}