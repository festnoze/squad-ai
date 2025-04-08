How to create a testset from RAGAS evaluations ?

- Call endpoint:` /rag/evaluation/create-QA-dataset` from the Public Site Chatbot API, accessible directly from: [RAG Chatbot API - Swagger UI](http://localhost:8281/docs#/Evaluation/create_q_and_a_dataset_from_existing_summary_and_questions_objects_async_rag_evaluation_create_QA_dataset_post). It extract a subset of all Questions/Chunks loaded as *trainings_objects* from '`outputs/trainings.json`'
  
  - "**samples_count_by_metadata**" define the count of items to extract for each value of the metadata: `training_info_type`.
  
  - "**output_file**" the excel file to be created, like '`example.json`'
  
  - "**limited_to_specified_metadata**" allow to limit to a specified value of the metadata: `training_info_type` within the allowed values: **summary / bref / header-training / programme / cards-diploma / methode / modalites / financement / simulation / metiers / academic_level**

- It creates the files: '`./outputs/example.json`' and '`./outputs/example.xlsx`'.

- Copy the '`./outputs/example.xlsx`' file into: `C:\Dev\squad-ai\Chatbot-Studi.com\QA Dataset Selection\outputs`.

- Open the `QA Dataset Selection` front-end via VS code, or by calling : `start_UI_data_selection.bat` with the adapted files in args (in `launch.json` or the bat file iteself). 

- Select (and modify) the questions/answers pairs which are adapted for the testset.

- Save before changing page (selected items will be added to the existing file).

- Copy the output file, let's say: `example_selected.xlsx` from the current '`./outputs`' folder, and copy it into the Public Site Chatbot API '`./outputs`' folder.

- Call the endpoint` /rag/evaluation/run-inference` from the Public Site Chatbot API, accessible directly from: [RAG Chatbot API - Swagger UI](http://localhost:8281/docs#/Evaluation/run_questions_dataset_through_rag_inference_pipeline_and_save_async_rag_evaluation_run_inference_post). And specify the file of the selected items, like: `example_selected.xlsx` and the output file (json only?), like: `example_selected_with_inference.json`.  It runs the inference pipeline upon each selected Questions, and add to the table two columns : the retrieved chunks, and the response.

- Then, call the endpoint: `/rag/evaluation/evaluate` from the Public Site Chatbot API, accessible directly from: [RAG Chatbot API - Swagger UI](http://localhost:8281/docs#/Evaluation/run_ragas_evaluation_and_upload_async_rag_evaluation_evaluate_post). It runs the RAGAS evaluations metrics against the specified json file (select the previous: `example_selected_with_inference.json` file).

- A link of the RAGAS evaluation results is displayed into the terminal, which allow to see each metrics result for each item.


