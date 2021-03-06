from torch.utils.data.dataset import Dataset
import torch
import csv
from nltk.tokenize import sent_tokenize, word_tokenize
import numpy as np
import sys
import os
from transformers import *
#For loading large text corpora
class MyDataset(Dataset):
    def __init__(self, data_path, pos_path, max_length):
        super(MyDataset, self).__init__()
        preprocess_text = data_path[:-4]+'.npy'
        self.sentences = np.load(preprocess_text, mmap_mode='r')
        #sentences = sentences.astype(np.float16)
        #np.save(f'{data_path[:-4]}.snpy', sentences)
        bd_file = data_path[:-4]+'.index'
        bd_list = []
        texts = []
        labels = []
        pos = []
        pos_dict = {}
        bd_pairs = []
        
        with open(pos_path) as f:
            for i in f:
                i = i.strip()
                i = i.split(',')
                pos_dict[int(i[0])] =[int(j) for j in i[1:]] 
 
 
        with open(bd_file) as f:
            count = 0
            for i in f:
                count += int(i.strip())
                bd_list.append(count)

        with open(data_path) as csv_file:
            reader = csv.reader(csv_file, quotechar='"')
            bd_next = 0
            for idx, line in enumerate(reader):
                cite_pos = []
                bd = bd_list[2*idx]
                label = int(line[0])
                text_1 = (bd_next,bd)
                bd_next = bd_list[2*idx+1]
                text_2 = (bd,bd_next)
                bd_pairs.append((text_1, text_2))
                labels.append(label)
                pos.append(pos_dict.get(idx,[]))

        #texts = self.unifying(texts, bd_list)
        labels = np.array(labels)
        self.texts = bd_pairs
        self.labels = labels
        self.pos = pos
        self.mask = [] 

    def get_pos(self):
        return self.pos

    def __len__(self):
        return len(self.labels)

    def process(self, bd):
        i = self.sentences[bd[0]:bd[1]]
        i = np.array(i)
        max_length = 60 
        if i.shape[0] < max_length:
            padding = np.zeros((max_length-i.shape[0],1024))
            doc = np.concatenate((i, padding))
            mask = [1]*i.shape[0]+[0]*(max_length-i.shape[0])
        else:
            mask = [1]*max_length	    
            doc = i[:max_length]
        self.collect_mask(mask)
        return doc, np.array(mask) 

    def collect_mask(self, mask):
        self.mask.append(mask)

    def get_mask(self):
        return np.array(self.mask)

    def __getitem__(self, index):
        cite_pos = self.pos[index]
        label = self.labels[index]
        text_1, mask_1 = self.process(self.texts[index][0])
        text_2, mask_2 = self.process(self.texts[index][1])
        #cls_ = self.process(text_1, text_2)
        cls1 = text_1
        cls2 = text_2
        return cls1.astype(np.float32), cls2.astype(np.float32), label, cite_pos

if __name__ == '__main__':
    test = MyDataset(data_path="../data/ex.csv")
    print(test.__getitem__(index=8)[0].shape)
    print(test.__getitem__(index=8)[1].shape)
