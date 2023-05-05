#  Copyright 2021-present, the Recognai S.L. team.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from sqlalchemy.orm import Session

from argilla.server.contexts import datasets
from argilla.server.database import get_db
from argilla.server.elasticsearch import ElasticSearchEngine, get_search_engine
from argilla.server.policies import DatasetPolicyV1, authorize
from argilla.server.schemas.v1.datasets import (
    Dataset,
    DatasetCreate,
    Datasets,
    Field,
    FieldCreate,
    Fields,
    Metrics,
    Question,
    QuestionCreate,
    Questions,
    RecordInclude,
    Records,
    RecordsCreate,
)
from argilla.server.security import auth
from argilla.server.security.model import User

LIST_DATASET_RECORDS_LIMIT_DEFAULT = 50
LIST_DATASET_RECORDS_LIMIT_LTE = 1000

router = APIRouter(tags=["datasets"])


def _get_dataset(db: Session, dataset_id: UUID):
    dataset = datasets.get_dataset_by_id(db, dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with id `{dataset_id}` not found",
        )

    return dataset


@router.get("/me/datasets", response_model=Datasets)
def list_current_user_datasets(
    *,
    db: Session = Depends(get_db),
    current_user: User = Security(auth.get_current_user),
):
    authorize(current_user, DatasetPolicyV1.list)

    if current_user.is_admin:
        return Datasets(items=datasets.list_datasets(db))
    else:
        return Datasets(items=current_user.datasets)


@router.get("/datasets/{dataset_id}/fields", response_model=Fields)
def list_dataset_fields(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    current_user: User = Security(auth.get_current_user),
):
    dataset = _get_dataset(db, dataset_id)

    authorize(current_user, DatasetPolicyV1.get(dataset))

    return Fields(items=dataset.fields)


@router.get("/datasets/{dataset_id}/questions", response_model=Questions)
def list_dataset_questions(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    current_user: User = Security(auth.get_current_user),
):
    dataset = _get_dataset(db, dataset_id)

    authorize(current_user, DatasetPolicyV1.get(dataset))

    return Questions(items=dataset.questions)


@router.get("/me/datasets/{dataset_id}/records", response_model=Records, response_model_exclude_unset=True)
def list_current_user_dataset_records(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    include: Optional[List[RecordInclude]] = Query([]),
    offset: int = 0,
    limit: int = Query(default=LIST_DATASET_RECORDS_LIMIT_DEFAULT, lte=LIST_DATASET_RECORDS_LIMIT_LTE),
    current_user: User = Security(auth.get_current_user),
):
    dataset = _get_dataset(db, dataset_id)

    authorize(current_user, DatasetPolicyV1.get(dataset))

    records = datasets.list_records_by_dataset_id_and_user_id(
        db, dataset_id, current_user.id, include=include, offset=offset, limit=limit
    )

    return Records(
        items=[record.__dict__ for record in records],
        total=datasets.count_records_by_dataset_id(db, dataset_id),
    )


@router.get("/datasets/{dataset_id}", response_model=Dataset)
def get_dataset(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    current_user: User = Security(auth.get_current_user),
):
    dataset = _get_dataset(db, dataset_id)

    authorize(current_user, DatasetPolicyV1.get(dataset))

    return dataset


@router.get("/me/datasets/{dataset_id}/metrics", response_model=Metrics)
def get_current_user_dataset_metrics(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    current_user: User = Security(auth.get_current_user),
):
    dataset = _get_dataset(db, dataset_id)

    authorize(current_user, DatasetPolicyV1.get(dataset))

    return {
        "records": {
            "count": datasets.count_records_by_dataset_id(db, dataset_id),
        },
        "responses": {
            "count": datasets.count_responses_by_dataset_id_and_user_id(db, dataset_id, current_user.id),
            "submitted": datasets.count_submitted_responses_by_dataset_id_and_user_id(db, dataset_id, current_user.id),
            "discarded": datasets.count_discarded_responses_by_dataset_id_and_user_id(db, dataset_id, current_user.id),
        },
    }


@router.post("/datasets", status_code=status.HTTP_201_CREATED, response_model=Dataset)
def create_dataset(
    *,
    db: Session = Depends(get_db),
    dataset_create: DatasetCreate,
    current_user: User = Security(auth.get_current_user),
):
    authorize(current_user, DatasetPolicyV1.create)

    if datasets.get_dataset_by_name_and_workspace_id(db, dataset_create.name, dataset_create.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dataset with name `{dataset_create.name}` already exists for workspace with id `{dataset_create.workspace_id}`",
        )

    return datasets.create_dataset(db, dataset_create)


@router.post("/datasets/{dataset_id}/fields", status_code=status.HTTP_201_CREATED, response_model=Field)
def create_dataset_field(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    field_create: FieldCreate,
    current_user: User = Security(auth.get_current_user),
):
    authorize(current_user, DatasetPolicyV1.create_field)

    dataset = _get_dataset(db, dataset_id)

    if datasets.get_field_by_name_and_dataset_id(db, field_create.name, dataset_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Field with name `{field_create.name}` already exists for dataset with id `{dataset_id}`",
        )

    # TODO: We should split API v1 into different FastAPI apps so we can customize error management.
    # After mapping ValueError to 422 errors for API v1 then we can remove this try except.
    try:
        return datasets.create_field(db, dataset, field_create)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))


@router.post("/datasets/{dataset_id}/questions", status_code=status.HTTP_201_CREATED, response_model=Question)
def create_dataset_question(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    question_create: QuestionCreate,
    current_user: User = Security(auth.get_current_user),
):
    authorize(current_user, DatasetPolicyV1.create_question)

    dataset = _get_dataset(db, dataset_id)

    if datasets.get_question_by_name_and_dataset_id(db, question_create.name, dataset_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Question with name `{question_create.name}` already exists for dataset with id `{dataset_id}`",
        )

    # TODO: We should split API v1 into different FastAPI apps so we can customize error management.
    # After mapping ValueError to 422 errors for API v1 then we can remove this try except.
    try:
        return datasets.create_question(db, dataset, question_create)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))


@router.post("/datasets/{dataset_id}/records", status_code=status.HTTP_204_NO_CONTENT)
def create_dataset_records(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    records_create: RecordsCreate,
    current_user: User = Security(auth.get_current_user),
):
    authorize(current_user, DatasetPolicyV1.create_records)

    dataset = _get_dataset(db, dataset_id)

    # TODO: We should split API v1 into different FastAPI apps so we can customize error management.
    # After mapping ValueError to 422 errors for API v1 then we can remove this try except.
    try:
        datasets.create_records(db, dataset, current_user, records_create)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))


@router.put("/datasets/{dataset_id}/publish", response_model=Dataset)
async def publish_dataset(
    *,
    db: Session = Depends(get_db),
    search_engine: ElasticSearchEngine = Depends(get_search_engine),
    dataset_id: UUID,
    current_user: User = Security(auth.get_current_user),
):
    authorize(current_user, DatasetPolicyV1.publish)

    dataset = _get_dataset(db, dataset_id)

    # TODO: We should split API v1 into different FastAPI apps so we can customize error management.
    # After mapping ValueError to 422 errors for API v1 then we can remove this try except.
    try:
        return await datasets.publish_dataset(db, search_engine, dataset)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err))


@router.delete("/datasets/{dataset_id}", response_model=Dataset)
def delete_dataset(
    *,
    db: Session = Depends(get_db),
    dataset_id: UUID,
    current_user: User = Security(auth.get_current_user),
):
    authorize(current_user, DatasetPolicyV1.delete)

    dataset = _get_dataset(db, dataset_id)

    datasets.delete_dataset(db, dataset)

    return dataset
