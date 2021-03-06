# coding=utf-8
# Copyright 2018 The Google AI Language Team Authors and The HuggingFace Inc. team.
# Copyright (c) 2018, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Fine-tuning the library models for language modeling on a text file (GPT, GPT-2, BERT, RoBERTa).
GPT and GPT-2 are fine-tuned using a causal language modeling (CLM) loss while BERT and RoBERTa are fine-tuned
using a masked language modeling (MLM) loss.
"""


import logging
import math
import os
from dataclasses import dataclass, field
from typing import Optional
from transformers import (
    MODEL_WITH_LM_HEAD_MAPPING,
    HfArgumentParser,
    PreTrainedTokenizer,
    Trainer,
    TrainingArguments,
    set_seed,
)
from transformers import LongformerForMaskedLM, LongformerTokenizer
# from longformer.longformer import LongformerForMaskedLM, LongformerConfig
from pretraining.corpus_preprocessing import TextDataset
from pretraining.cdmlm_data_collector import DataCollatorForLanguageModeling
logger = logging.getLogger(__name__)


MODEL_CONFIG_CLASSES = list(MODEL_WITH_LM_HEAD_MAPPING.keys())
MODEL_TYPES = tuple(conf.model_type for conf in MODEL_CONFIG_CLASSES)


@dataclass
class ModelArguments:
    """
    Arguments pertaining to which model/config/tokenizer we are going to fine-tune, or train from scratch.
    """

    model_name_or_path: Optional[str] = field(
        default='/home/t-avic/PycharmProjects/coref_former/longformer-base-4096/',
        metadata={
            "help": "The model checkpoint for weights initialization. Leave None if you want to train a model from scratch."
        },
    )
    model_type: Optional[str] = field(
        default=None,
        metadata={"help": "If training from scratch, pass a model type from the list: " + ", ".join(MODEL_TYPES)},
    )
    config_name: Optional[str] = field(
        default='/home/t-avic/PycharmProjects/coref_former/longformer-base-4096/', metadata={"help": "Pretrained config name or path if not the same as model_name"}
    )
    tokenizer_name: Optional[str] = field(
        default='RobertaTokenizer', metadata={"help": "Pretrained tokenizer name or path if not the same as model_name"}
    )
    cache_dir: Optional[str] = field(
        default='/home/t-avic/PycharmProjects/coref_former/finetuned', metadata={"help": "Where do you want to store the pretrained models downloaded from s3"}
    )


@dataclass
class DataTrainingArguments:
    """
    Arguments pertaining to what data we are going to input our model for training and eval.
    """

    train_data_file: Optional[str] = field(
        default='train.txt.src', metadata={"help": "The input training data file (a text file)."}
    )
    eval_data_file: Optional[str] = field(
        default=None,
        metadata={"help": "An optional input evaluation data file to evaluate the perplexity on (a text file)."},
    )
    line_by_line: bool = field(
        default=False,
        metadata={"help": "Whether distinct lines of text in the dataset are to be handled as distinct sequences."},
    )
    globalize_special_tokens: bool = field(
        default=False,
        metadata={"help": "Whether only the special tokens are assigned with global attention."},
    )
    mlm: bool = field(
        default=True, metadata={"help": "Train with masked-language modeling loss instead of language modeling."}
    )
    mlm_probability: float = field(
        default=0.15, metadata={"help": "Ratio of tokens to mask for masked language modeling loss"}
    )

    block_size: int = field(
        default=-1,
        metadata={
            "help": "Optional input sequence length after tokenization."
            "The training dataset will be truncated in block of this size for training."
            "Default to the model max input length for single sentence inputs (take into account special tokens)."
        },
    )
    overwrite_cache: bool = field(
        default=False, metadata={"help": "Overwrite the cached training and evaluation sets"}
    )


def get_dataset(args: DataTrainingArguments, tokenizer: PreTrainedTokenizer, evaluate=False, local_rank=-1):
    file_path = args.eval_data_file if evaluate else args.train_data_file
    return TextDataset(
        tokenizer=tokenizer,split='dev' if evaluate else 'train', file_path=file_path, block_size=args.block_size, local_rank=local_rank
    )


def main():
    parser = HfArgumentParser((ModelArguments, DataTrainingArguments, TrainingArguments))
    model_args, data_args, training_args = parser.parse_args_into_dataclasses()

    if data_args.eval_data_file is None and training_args.do_eval:
        raise ValueError(
            "Cannot do evaluation without an evaluation data file. Either supply a file to --eval_data_file " 
            "or remove the --do_eval argument."
        )

    if (
        os.path.exists(training_args.output_dir)
        and os.listdir(training_args.output_dir)
        and training_args.do_train
        and not training_args.overwrite_output_dir
    ):
        raise ValueError(
            f"Output directory ({training_args.output_dir}) already exists and is not empty. Use --overwrite_output_dir to overcome."
        )

    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO if training_args.local_rank in [-1, 0] else logging.WARN,
    )
    logger.warning(
        "Process rank: %s, device: %s, n_gpu: %s, distributed training: %s, 16-bits training: %s",
        training_args.local_rank,
        training_args.device,
        training_args.n_gpu,
        bool(training_args.local_rank != -1),
        training_args.fp16,
    )
    logger.info("Training/evaluation parameters %s", training_args)

    set_seed(training_args.seed)

    model = LongformerForMaskedLM.from_pretrained('allenai/longformer-base-4096')
    tokenizer = LongformerTokenizer.from_pretrained('allenai/longformer-base-4096')
    tokenizer.add_tokens(['<doc-s>'], special_tokens=True)
    tokenizer.add_tokens(['</doc-s>'], special_tokens=True)

    data_args.block_size = 4096

    train_dataset = get_dataset(data_args, tokenizer=tokenizer, local_rank=training_args.local_rank)
    model.resize_token_embeddings(len(tokenizer))
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer, mlm=data_args.mlm, mlm_probability=data_args.mlm_probability, globalize_special_tokens=data_args.globalize_special_tokens
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        data_collator=data_collator,
        train_dataset=train_dataset,
        # eval_dataset=eval_dataset,
        prediction_loss_only=True,
    )

    model_path = (
        model_args.model_name_or_path
        if model_args.model_name_or_path is not None and os.path.isdir(model_args.model_name_or_path)
        else None
    )
    trainer.train(model_path=model_path)
    if trainer.is_world_master():
        tokenizer.save_pretrained(training_args.output_dir)

    results = {}
    logger.info("*** Evaluate ***")

    eval_output = trainer.evaluate()

    perplexity = math.exp(eval_output["loss"])
    result = {"perplexity": perplexity}

    output_eval_file = os.path.join(training_args.output_dir, "eval_results_lm.txt")
    with open(output_eval_file, "w") as writer:
        logger.info("***** Eval results *****")
        for key in sorted(result.keys()):
            logger.info("  %s = %s", key, str(result[key]))
            writer.write("%s = %s\n" % (key, str(result[key])))

    results.update(result)

    return results


if __name__ == "__main__":
    main()
