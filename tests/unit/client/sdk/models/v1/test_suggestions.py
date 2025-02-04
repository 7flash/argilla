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

from argilla.client.sdk.v1.suggestions.models import SuggestionModel as ClientSchema
from argilla.server.schemas.v1.suggestions import Suggestion as ServerSchema


def test_suggestion_schema(helpers) -> None:
    assert helpers.are_compatible_api_schemas(ClientSchema.schema(), ServerSchema.schema())
